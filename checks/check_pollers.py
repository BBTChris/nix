#!/usr/bin/env python3
"""check_pollers -- verify.py gate: §6.4's two pollers exist, own the caches
the spec gives them, demote under push, contain a hung venue socket, and DO NOT
hold a second live-margin table.

Subject: `scripts/nixrisk/pollers.py`. The gate loads it from `ctx.nix_home`
and DRIVES it -- on a real event loop, with real coroutines -- except where an
arm is explicitly about the shape of the file.

---

## THE THREE DEFECTS THIS GATE EXISTS TO CATCH

**1. A SECOND MARGIN TABLE.** §6.4's v1.3 lock is unambiguous: *"live current
margin per symbol is NOT a separate table or its own shared-memory block"*,
because *"independent tables tick on independent clocks, so a sizing pass could
read fresh margin against slightly stale balance."* A "fast, seconds" margin
poller is exactly where a live per-symbol margin figure wants to live, and one
that cached it would look correct and pass its own tests. ARM LOCK is an AST
scan for any expression naming the live field, plus a runtime check that every
published row is a §6.3 `MarginBaseline`.

**2. A DEMOTION THAT IS A LABEL.** §6.4: *"event-driven updates are primary and
polling demotes to fallback/audit."* A `mode` attribute that flips to
`FALLBACK_AUDIT` while the poller keeps its cadence has demoted nothing. ARM
PUSH measures the CADENCE either side of a push, requires it to widen, requires
the poller to re-promote when the pushes stop **with no event to tell it**, and
requires the constructor to REFUSE an audit interval that is not wider.

**3. AN `async def` THAT BLOCKS.** `calendar_seam.py` made `poll_once` async
for CONTAINMENT (*"a hung broker socket must cost one suspended coroutine and
not one blocked pool worker"*) and `refresh` async for DURATION (*"cooperative
yielding during a long rebuild so a slow calendar refresh cannot starve the
fast margin poll sharing the pool"*). Both are properties of the loop, not of
the keyword: a coroutine that awaits only at its start and its end is a
blocking function with `async` written on it. ARM POOL hangs a fetch forever
and measures that the calendar still completes, and counts how many times a
competing task is scheduled DURING one refresh.

## debug.md §7.12 -- THE STANDING QUESTION: how could this gate be GREEN while
## the property is FALSE?

1. **The subject could fail to load and a `try/except` could swallow it.**
   *Closed:* `load_subject` returns a complaint naming the import error and
   `run`'s catch-all is CANNOT_MEASURE, never PASS (§17).

2. **ARM POOL could measure a yield that the DRIVE supplies rather than the
   subject.** If the competing task itself slept for a duration, it would be
   descheduled by the timer and the count would say nothing about the calendar.
   *Closed:* the competing task awaits `asyncio.sleep(0)` -- a bare
   reschedule with no timer -- so every tick it records is a point at which the
   REFRESH gave the loop back. With the yield removed from the rebuild loop the
   count collapses to one, which is exactly what the can-fail suite plants.

3. **ARM POOL's symbol count could be so small that "yields per symbol" and
   "yields at the edges" are the same number.** *Closed:* `FLOORS["symbols"]`
   -- a floor, not today's count (C.4) -- and the tick count is required to be
   at least half of it, so a two-symbol rebuild cannot satisfy the arm.

4. **ARM LOCK could ban a string and be defeated by an attribute.** Or the
   reverse. *Closed both ways:* the AST arm rejects `ast.Attribute` nodes AND
   the runtime arm asserts the published row TYPE, so a poller that reached the
   live figure through a differently-named local still publishes the wrong
   object and reddens.

5. **ARM LOCK's banned name could be typed here and drift from the module.**
   *Closed:* the name is read out of the subject's own `LIVE_MARGIN_FIELD`
   constant, so the gate and the module cannot disagree about what is banned.

6. **ARM PUSH could pass on a poller that always reports FALLBACK_AUDIT.**
   *Closed:* the arm requires `PRIMARY` before any push AND after the idle
   window, so both edges are controls for each other.

7. **The guard arm could pass on a poller that discards EVERYTHING.** A
   producer that admitted nothing would never regress a key. *Closed:* the arm
   requires the fresher reading to be ADMITTED and the cache to carry it, in
   the same drive that requires the older one to be discarded.

8. **Every arm could run on an empty cache.** *Closed:* `FLOORS["symbols"]`
   and `FLOORS["publishes"]` require a real population and real publishes
   before any verdict, and a drive below either is CANNOT_MEASURE.

9. **THE ONE THIS GATE DOES NOT CLOSE, stated rather than implied.** ARM
   POOL's CONTAINMENT half -- *the calendar refresh completed while a margin
   fetch hung forever* -- has **no can-fail plant**, because the defect it
   describes does not produce a red: a poller that genuinely blocked the loop
   would make this gate HANG, and a hanging gate is a timeout, not a verdict.
   What IS plantable is ARM SHAPE (the verb is not a coroutine function at all)
   and ARM POOL's YIELD half (the count collapses), and both are planted in
   `scripts/tests/test_check_pollers.py`. The containment drive is therefore a
   POSITIVE observation with a CANNOT_MEASURE guard (`margin_hung`) and no
   demonstrated negative, and that is the honest description of it. CHECK-DEBT
   carries the gap rather than a paragraph claiming otherwise.

## C.9 -- WHAT THIS GATE DELIBERATELY DOES NOT MEASURE

* `checks/check_staleness.py` owns `scripts/nixrisk/freshness.py`: the
  time-since-last-arrival measure, the retry window, the clock-skew monitor and
  the guard CLASS. This gate owns whether the two PRODUCERS route their
  readings through it and behave on the loop.
* `checks/check_calendar_schema.py` owns `calendar_seam.py` -- the port
  declarations, the UTC canonicality of the calendar DATA, and the read-only
  verb ban. This gate imports those Protocols and judges the implementations
  against them; it re-proves nothing about the seam itself.
* `checks/check_allocator_mirror.py` owns the CONSUMER-side §6.4b guard over
  the published financial picture. This one is the PRODUCER side over venue
  stamps, a different seam with different keys -- see `pollers.py`'s docstring
  table. Neither can stand in for the other.
* `checks/check_state_bus.py` owns the transport. These pollers publish into an
  injected sink; nothing here measures ZeroMQ.
* `nixrisk/flatten.py` owns the flatten and the HALT semantics belong
  elsewhere. §6.4 splits detection from execution and this gate stays on the
  detection side.

## NON-CORRECTABLE

The subject is declared source. A gate that rewrote the poller would make its
own verdict true by construction.
"""

from __future__ import annotations

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
import asyncio
import importlib
import inspect
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
DEPENDS_ON: tuple[str, ...] = ()
#: The subject is imported from `ctx.nix_home` (sys.path/sys.modules mutated and
#: restored) and driven on a private `asyncio` event loop created and closed by
#: this process. No port is bound, no socket is dialled, nothing is written.
RESOURCES: tuple[str, ...] = ("interpreter:sys.path", "interpreter:sys.modules")
TIME_BOUND = False
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is declared source; a repair that rewrote the poller would "
    "make this gate's own verdict true by construction"
)
SUBJECTS: tuple[str, ...] = ("scripts/nixrisk/pollers.py",)

NAME = "check_pollers"

REL_POLLERS = "scripts/nixrisk/pollers.py"
REL_FRESHNESS = "scripts/nixrisk/freshness.py"
REL_CONFIG = "risks/staleness.config.json"
REL_SEAM = "scripts/nixrisk/calendar_seam.py"

FLOORS: dict[str, int] = {
    # CLAUDE.md fixes operating scope at 1-5 concurrent instruments; the pool
    # drive runs 30 so "yields per symbol" and "yields at the edges" are
    # different numbers by a wide margin. A FLOOR (C.4): nothing legitimate
    # shrinks a rebuild population below this and still demonstrates duration.
    "symbols": 30,
    # A cache that never published cannot be judged on what it published.
    "publishes": 2,
    # Every arm the docstring enumerates.
    "arms": 8,
}

#: Both pollers are driven against the SAME §12A knob names their module
#: declares; nothing here is typed twice.
DRIVE_SYMBOL = "ES"
OTHER_SYMBOL = "NQ"


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
    pollers: Any
    freshness: Any
    seam: Any


_PREFIX = "nixrisk"


def load_subject(home: Path) -> tuple[_Subject | None, str]:
    """Import the subject FROM `home`, purging and restoring `sys.modules`.

    `check_limiter_gate.load_subject`'s reason: a check that ran once against
    the repo would otherwise hand back the repo's module for every subsequent
    tree, and a plant that is never loaded is a plant that cannot fail.
    """
    scripts = home / "scripts"
    if not (scripts / "nixrisk" / "pollers.py").is_file():
        return None, f"{REL_POLLERS} is not on disk under {home} -- nothing to drive"
    saved_path = list(sys.path)
    saved_mods = {
        key: value
        for key, value in sys.modules.items()
        if key == _PREFIX or key.startswith(f"{_PREFIX}.")
    }
    for key in saved_mods:
        del sys.modules[key]
    sys.path.insert(0, str(scripts.resolve()))
    try:
        seam = importlib.import_module("nixrisk.calendar_seam")
        freshness = importlib.import_module("nixrisk.freshness")
        pollers = importlib.import_module("nixrisk.pollers")
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return None, (
            f"{REL_POLLERS} would not import from {home}: {type(exc).__name__}: {exc}"
        )
    finally:
        for key in [
            key
            for key in list(sys.modules)
            if key == _PREFIX or key.startswith(f"{_PREFIX}.")
        ]:
            del sys.modules[key]
        sys.modules.update(saved_mods)
        sys.path[:] = saved_path
    return _Subject(pollers, freshness, seam), ""


def _subject_defects(home: Path) -> CheckResult | None:
    missing = [
        rel
        for rel in (REL_POLLERS, REL_FRESHNESS, REL_CONFIG, REL_SEAM)
        if not (home / rel).is_file()
    ]
    if not missing:
        return None
    return _cannot(
        f"absent subject(s) under {home}: {', '.join(missing)} -- a property "
        "proven while its subject is unavailable is not proven (§17)"
    )


def _config_values(home: Path) -> tuple[dict[str, Any], str]:
    try:
        raw = json.loads((home / REL_CONFIG).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {}, f"{REL_CONFIG} could not be read or parsed: {exc}"
    if not isinstance(raw, dict):
        return {}, f"{REL_CONFIG}: top level is {type(raw).__name__}, expected object"
    return {k: v for k, v in raw.items() if not k.startswith("_")}, ""


# ---------------------------------------------------------------------------
# Drive rig
# ---------------------------------------------------------------------------


class _Clock:
    """A settable UTC clock — every cadence below is driven, never waited out."""

    EPOCH = datetime(2026, 8, 15, 12, 0, 0, tzinfo=UTC)

    def __init__(self) -> None:
        self.now = self.EPOCH

    def __call__(self) -> datetime:
        return self.now

    def set_ms(self, offset_ms: float) -> datetime:
        """Move to EPOCH + `offset_ms` and return the new instant."""
        self.now = self.EPOCH + timedelta(milliseconds=offset_ms)
        return self.now


class _Rig(NamedTuple):
    clock: _Clock
    tracker: Any
    demotion: Any
    poll_ms: float
    audit_ms: float
    idle_ms: float


def _rig(subject: _Subject, values: dict) -> _Rig:
    clock = _Clock()
    policy = subject.freshness.StalenessPolicy.from_values(values)
    tracker = subject.freshness.FreshnessTracker(policy, clock=clock)
    poll_ms = policy.threshold_ms(subject.pollers.MARGIN_FEED) / 5.0
    audit_ms = poll_ms * 4.0
    idle_ms = poll_ms * 10.0
    demotion = subject.pollers.PushDemotion(
        poll_interval_ms=poll_ms,
        audit_interval_ms=audit_ms,
        push_idle_ms=idle_ms,
        clock=clock,
    )
    return _Rig(clock, tracker, demotion, poll_ms, audit_ms, idle_ms)


def _baseline_rows(
    subject: _Subject, symbols: list[str], at: datetime, seq: int
) -> list:
    seam, pollers = subject.seam, subject.pollers
    return [
        pollers.StampedBaseline(
            baseline=seam.MarginBaseline(
                symbol=sym, level=1000.0 + seq, accepted_at=at
            ),
            stamp=seam.FreshnessStamp(
                feed=pollers.MARGIN_FEED, as_of=at, source_seq=seq
            ),
        )
        for sym in symbols
    ]


def _margin_poller(
    subject: _Subject, rig: _Rig, symbols: list[str]
) -> tuple[Any, list]:
    """A `MarginPoller` whose fetch advances the venue stamp on every call."""
    state = {"seq": 0}
    log: list[str] = []

    async def fetch() -> list:
        state["seq"] += 1
        log.append(f"margin:{state['seq']}")
        await asyncio.sleep(0)
        return _baseline_rows(subject, symbols, rig.clock(), state["seq"])

    return (
        subject.pollers.MarginPoller(
            fetch=fetch, tracker=rig.tracker, demotion=rig.demotion
        ),
        log,
    )


def _calendar_poller(subject: _Subject, rig: _Rig, symbols: list[str]) -> Any:
    seam, pollers = subject.seam, subject.pollers

    def build(symbol: str) -> tuple:
        return (
            seam.Window(
                kind=seam.WindowKind.EOD,
                symbol=symbol,
                start=rig.clock(),
                end=rig.clock() + timedelta(minutes=20),
                entry_only=True,
                source="check_pollers drive",
            ),
        )

    def stamp_for(symbol: str) -> Any:
        del symbol
        return seam.FreshnessStamp(
            feed=pollers.CALENDAR_FEED, as_of=rig.clock(), source_seq=1
        )

    return pollers.CalendarPoller(
        symbols=symbols,
        build=build,
        stamp_for=stamp_for,
        tracker=rig.tracker,
        clock=rig.clock,
        demotion=rig.demotion,
    )


# ---------------------------------------------------------------------------
# Arms
# ---------------------------------------------------------------------------


def _arm_shape(subject: _Subject) -> tuple[list[Finding], int, str]:
    """ARM SHAPE: each verb is async or sync exactly as `calendar_seam.py` declared.

    Structural and it runs FIRST, because every behavioural arm below stands on
    it: a `publish` that is a coroutine function returns an un-awaited coroutine
    and the cache never changes, at which point the drives measure an empty
    object and report CANNOT_MEASURE rather than the defect. The shape is also
    the half that is separately plantable -- ARM POOL's containment drive has no
    can-fail plant, because its negative outcome is a hang rather than a red,
    and saying so is the honest account of what that drive proves.
    """
    findings: list[Finding] = []
    checked = 0
    #: (class, verb, must_be_coroutine, the seam's own reason)
    expected = (
        (
            "MarginPoller",
            "poll_once",
            True,
            (
                "CONTAINMENT -- 'a hung broker socket must cost one suspended "
                "coroutine and not one blocked pool worker'; a synchronous poll "
                "on the §10 shared pool blocks a pool worker instead"
            ),
        ),
        (
            "CalendarPoller",
            "refresh",
            True,
            (
                "DURATION -- cooperative yielding during a long rebuild so a "
                "slow calendar refresh cannot starve the fast margin poll "
                "sharing the pool"
            ),
        ),
        (
            "MarginPoller",
            "publish",
            False,
            (
                "§12.7 -- an awaitable publish opens the window in which a "
                "subscriber's mirror observes a half-built table, the state "
                "§12.7 calls 'incomplete => treated as stale'"
            ),
        ),
        (
            "CalendarPoller",
            "publish",
            False,
            (
                "§12.7 -- same reason; the verb returns when the bytes are "
                "consistent, or it is not a publish"
            ),
        ),
    )
    for cls_name, verb, must_be_async, why in expected:
        func = getattr(getattr(subject.pollers, cls_name, None), verb, None)
        if func is None:
            findings.append(
                Finding(
                    f"{REL_POLLERS}:{cls_name}",
                    f"declares no {verb!r} -- the port `calendar_seam.py` gave "
                    "this class has a verb missing",
                )
            )
            continue
        checked += 1
        is_async = inspect.iscoroutinefunction(func)
        if is_async is not must_be_async:
            findings.append(
                Finding(
                    f"{REL_POLLERS}:{cls_name}.{verb}",
                    f"is {'a' if is_async else 'not a'} coroutine function; "
                    f"`calendar_seam.py` declares it "
                    f"{'ASYNCHRONOUS' if must_be_async else 'SYNCHRONOUS'} for "
                    f"{why}",
                )
            )
    if checked < len(expected):
        return (
            findings,
            checked,
            (
                f"only {checked} of {len(expected)} declared verbs were found, so "
                "the shape of the missing ones was not measured (§17)"
            ),
        )
    return findings, checked, ""


def _arm_ports(subject: _Subject, values: dict) -> tuple[list[Finding], int, str]:
    """ARM PORTS: every pair the module CLAIMS is resolved and isinstance-checked."""
    pairs = getattr(subject.pollers, "PORT_IMPLEMENTATIONS", ())
    if len(pairs) < 4:
        return (
            [],
            0,
            (
                f"{REL_POLLERS} declares {len(pairs)} port implementation(s); §6.4 "
                "gives each poller a poll verb and a read cache, so fewer than four "
                "pairs means a cache with no declared reader or a poller with no "
                "declared port (§17)"
            ),
        )
    rig = _rig(subject, values)
    symbols = [DRIVE_SYMBOL, OTHER_SYMBOL]
    instances = {
        "MarginPoller": _margin_poller(subject, rig, symbols)[0],
        "CalendarPoller": _calendar_poller(subject, rig, symbols),
    }
    findings: list[Finding] = []
    checked = 0
    for cls_name, port_name in pairs:
        obj = instances.get(cls_name)
        proto = getattr(subject.seam, port_name, None)
        if obj is None or proto is None:
            findings.append(
                Finding(
                    f"{REL_POLLERS}:PORT_IMPLEMENTATIONS",
                    f"claims {cls_name!r} satisfies {port_name!r}, but "
                    f"{'the class' if obj is None else 'the Protocol'} could not "
                    "be resolved -- a declaration over an absent subject",
                )
            )
            continue
        checked += 1
        if not isinstance(obj, proto):
            findings.append(
                Finding(
                    f"{REL_POLLERS}:{cls_name}",
                    f"does not satisfy {REL_SEAM}:{port_name}. The seam declared "
                    "this port in Phase 0.4 and nothing else implements it, so a "
                    "consumer written against the seam gets no producer",
                )
            )
    return findings, checked, ""


def _lock_ast_findings(tree: ast.AST, banned: str) -> list[Finding]:
    """No expression in the module may NAME the live per-symbol margin field,
    and the unified snapshot's type may not be imported here."""
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == banned:
            findings.append(
                Finding(
                    f"{REL_POLLERS}:{node.lineno}",
                    f"reads the LIVE per-symbol margin field {banned!r}. §6.4's "
                    "v1.3 lock: live current margin per symbol is NOT a separate "
                    "table -- the Limiter folds it into the one unified "
                    "financial-picture snapshot under one writer and one version "
                    "stamp. A copy here ticks on its own clock, and a sizing pass "
                    "would read fresh margin against slightly stale balance",
                )
            )
        if isinstance(node, ast.ImportFrom) and _imports_picture(node):
            findings.append(
                Finding(
                    f"{REL_POLLERS}:{node.lineno}",
                    "imports FinancialPicture. The unified snapshot is the "
                    "LIMITER's, written by one writer under one version stamp; "
                    "a poller holding it is a second surface for the same state "
                    "(§6.4 v1.3 lock)",
                )
            )
    return findings


def _imports_picture(node: ast.ImportFrom) -> bool:
    """`from nixrisk.picture|seam import ... FinancialPicture ...`."""
    if node.module not in {"nixrisk.picture", "nixrisk.seam"}:
        return False
    return any(alias.name == "FinancialPicture" for alias in node.names)


def _lock_runtime_findings(
    subject: _Subject, values: dict
) -> tuple[list[Finding], str]:
    """In FACT: every published row is a §6.3 baseline, not a live figure."""
    rig = _rig(subject, values)
    poller, _ = _margin_poller(subject, rig, [DRIVE_SYMBOL, OTHER_SYMBOL])
    asyncio.run(poller.poll_once())
    published = poller.published()
    if not published:
        return [], (
            "the margin poller published nothing after a poll, so the row TYPE "
            "could not be measured (§17)"
        )
    return [
        Finding(
            f"{REL_POLLERS}:MarginPoller.publish",
            f"published a {type(row).__name__} rather than a MarginBaseline. "
            "`calendar_seam.py` reserves this cache for §6.3's BASELINE -- the "
            "level a trailing edge waits to return to -- and anything else here "
            "is the second table §6.4 locks",
        )
        for row in published
        if not isinstance(row, subject.seam.MarginBaseline)
    ], ""


def _arm_lock(home: Path, subject: _Subject, values: dict) -> tuple[list[Finding], str]:
    """ARM LOCK (§6.4 v1.3): no second live-margin surface, in shape OR in fact."""
    banned = getattr(subject.pollers, "LIVE_MARGIN_FIELD", "")
    if not banned:
        return [], (
            f"{REL_POLLERS} declares no LIVE_MARGIN_FIELD, so this arm has no "
            "name to ban and would pass over an empty search (§17)"
        )
    try:
        tree = ast.parse((home / REL_POLLERS).read_text(encoding="utf-8"))
    except (OSError, SyntaxError) as exc:
        return [], f"{REL_POLLERS} could not be parsed: {exc} (§17)"
    findings = _lock_ast_findings(tree, banned)
    runtime, cannot = _lock_runtime_findings(subject, values)
    return findings + runtime, cannot


def _push_primary_before(poller, pollers) -> list[Finding]:
    """§6.4 makes polling primary until the user-sync websocket delivers."""
    if poller.mode is pollers.PollerMode.PRIMARY:
        return []
    return [
        Finding(
            f"{REL_POLLERS}:MarginPoller.mode",
            f"a poller that has seen NO push reports {poller.mode} -- §6.4 makes "
            "polling primary until the user-sync websocket delivers, so a "
            "poller that starts demoted has demoted to a feed that has not spoken",
        )
    ]


def _push_demotes(subject, poller, rig, before_ms: float) -> list[Finding]:
    """A push must be APPLIED, must demote, and must WIDEN the cadence."""
    pollers = subject.pollers
    at = rig.clock.set_ms(10.0)
    findings: list[Finding] = []
    if poller.on_push(_baseline_rows(subject, [DRIVE_SYMBOL], at, 50), at) < 1:
        findings.append(
            Finding(
                f"{REL_POLLERS}:MarginPoller.on_push",
                "a push carrying a NEWER venue stamp was not applied -- the "
                "push-preferred path admits nothing, so 'event-driven is "
                "primary' would mean the cache is fed by the fallback only",
            )
        )
    if poller.mode is not pollers.PollerMode.FALLBACK_AUDIT:
        findings.append(
            Finding(
                f"{REL_POLLERS}:MarginPoller.mode",
                f"a push arrived and the mode stayed {poller.mode} -- §6.4: "
                "event-driven updates are primary and polling DEMOTES to "
                "fallback/audit",
            )
        )
    after_ms = rig.demotion.interval_ms()
    if after_ms <= before_ms:
        findings.append(
            Finding(
                f"{REL_POLLERS}:PushDemotion.interval_ms",
                f"the poll cadence was {before_ms:.0f} ms before the push and "
                f"{after_ms:.0f} ms after it. A demotion that does not widen the "
                "cadence has changed a NAME and not a behaviour -- polling is "
                "still doing the work the websocket is credited with",
            )
        )
    return findings


def _push_re_promotes(subject, poller, rig, before_ms: float) -> list[Finding]:
    """Re-promotion happens by SILENCE. No event is delivered here on purpose."""
    pollers = subject.pollers
    rig.clock.set_ms(10.0 + rig.idle_ms * 2.0)
    findings: list[Finding] = []
    if poller.mode is not pollers.PollerMode.PRIMARY:
        findings.append(
            Finding(
                f"{REL_POLLERS}:PushDemotion.mode",
                f"the poller was still {poller.mode} after "
                f"{rig.idle_ms * 2:.0f} ms of push silence, past its "
                f"{rig.idle_ms:.0f} ms idle window. A dead websocket sends no "
                "failover event, so a mode that only changes on an event stays "
                "demoted through the outage the fallback exists to survive",
            )
        )
    if rig.demotion.interval_ms() != before_ms:
        findings.append(
            Finding(
                f"{REL_POLLERS}:PushDemotion.interval_ms",
                "the cadence did not return to the primary interval after "
                "re-promotion, so the fallback runs at the audit rate",
            )
        )
    return findings


def _push_refuses_equal_intervals(pollers, rig) -> list[Finding]:
    """A configuration that cannot demote would pass every other arm here."""
    try:
        pollers.PushDemotion(
            poll_interval_ms=rig.poll_ms,
            audit_interval_ms=rig.poll_ms,
            push_idle_ms=rig.idle_ms,
            clock=rig.clock,
        )
    except pollers.PollerUsageError:
        return []
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return [
            Finding(
                f"{REL_POLLERS}:PushDemotion.__init__",
                f"an equal audit interval raised {type(exc).__name__} rather "
                "than PollerUsageError -- a caller cannot distinguish it from "
                "any other fault",
            )
        ]
    return [
        Finding(
            f"{REL_POLLERS}:PushDemotion.__init__",
            "accepted an audit interval EQUAL to the poll interval. §6.4's "
            "demotion is the whole difference between implementing the "
            "push-preferred clause and gesturing at it, and a configuration "
            "that cannot demote would pass every other arm here",
        )
    ]


def _arm_push(subject: _Subject, values: dict) -> tuple[list[Finding], str]:
    """ARM PUSH (§6.4): the demotion changes CADENCE, and re-promotes on silence."""
    rig = _rig(subject, values)
    poller, _ = _margin_poller(subject, rig, [DRIVE_SYMBOL])
    primary_ms = rig.demotion.interval_ms()
    findings = _push_primary_before(poller, subject.pollers)
    findings += _push_demotes(subject, poller, rig, primary_ms)
    findings += _push_re_promotes(subject, poller, rig, primary_ms)
    findings += _push_refuses_equal_intervals(subject.pollers, rig)
    return findings, ""


def _arm_guard(subject: _Subject, values: dict) -> tuple[list[Finding], str]:
    """ARM GUARD (§6.4b at the PRODUCER): a late poll behind a fresher push is dropped."""
    rig = _rig(subject, values)
    symbols = [DRIVE_SYMBOL, OTHER_SYMBOL]
    poller, _ = _margin_poller(subject, rig, symbols)
    findings: list[Finding] = []

    fresh_at = rig.clock.set_ms(10_000.0)
    poller.on_push(_baseline_rows(subject, symbols, fresh_at, 90), fresh_at)
    held = poller.baseline(DRIVE_SYMBOL)
    if held is None:
        return findings, (
            "the push published no baseline for the driven symbol, so the "
            "regression control below has nothing to regress (§17)"
        )
    level_after_push = held.level

    before = rig.tracker.guard.discarded_older
    stale_at = _Clock.EPOCH
    poller.on_push(_baseline_rows(subject, symbols, stale_at, 1), stale_at)
    if rig.tracker.guard.discarded_older != before + len(symbols):
        findings.append(
            Finding(
                f"{REL_POLLERS}:MarginPoller._apply",
                f"a reading carrying an OLDER venue stamp moved "
                f"{rig.tracker.guard.discarded_older - before} of "
                f"{len(symbols)} keys through the guard. §6.4b: 'a slow poll "
                "landing after a fresher push is dropped, not applied' -- and "
                "the producer must route every reading through the guard, not "
                "only the ones it polled",
            )
        )
    now_held = poller.baseline(DRIVE_SYMBOL)
    if now_held is None or now_held.level != level_after_push:
        findings.append(
            Finding(
                f"{REL_POLLERS}:MarginPoller.baseline",
                f"the published baseline for {DRIVE_SYMBOL!r} REGRESSED after a "
                "stale reading. Discarded must mean not applied: §6.4b exists so "
                "no venue-sourced field can go backwards and mislead sizing",
            )
        )
    other = poller.baseline(OTHER_SYMBOL)
    if other is None:
        findings.append(
            Finding(
                f"{REL_POLLERS}:MarginPoller.baseline",
                f"{OTHER_SYMBOL!r} lost its baseline while {DRIVE_SYMBOL!r} was "
                "being guarded -- §6.4b's guard is PER KEY so a late update on "
                "one key can never regress another",
            )
        )
    return findings, ""


class _Ticker:
    """A competing task that records every time the loop gives it a turn.

    A BARE reschedule -- `asyncio.sleep(0)`, no timer -- so every tick is a
    point at which something else yielded. A duration-based sleep would count
    the loop's timer instead of the subject's yields, which is the arm passing
    while measuring nothing.
    """

    def __init__(self) -> None:
        self.ticks = 0
        self._running = True

    async def run(self) -> None:
        """Tick until stopped."""
        while self._running:
            self.ticks += 1
            await asyncio.sleep(0)

    def stop(self) -> None:
        """Stop ticking."""
        self._running = False


async def _pool_drive(subject: _Subject, rig: _Rig, symbols: list[str]) -> dict:
    """One event loop: a hung margin fetch, a long calendar refresh, a ticker."""
    hung = asyncio.Event()

    async def hang() -> list:
        await hung.wait()
        return _baseline_rows(subject, symbols[:1], rig.clock(), 1)

    hung_poller = subject.pollers.MarginPoller(
        fetch=hang, tracker=rig.tracker, demotion=rig.demotion
    )
    calendar = _calendar_poller(subject, rig, symbols)
    ticker = _Ticker()

    hung_task = asyncio.create_task(hung_poller.poll_once())
    tick_task = asyncio.create_task(ticker.run())
    await asyncio.sleep(0)
    before = ticker.ticks
    await calendar.refresh()
    stats = {
        "ticks_during": ticker.ticks - before,
        "calendar_publishes": calendar.publishes,
        "margin_hung": not hung_task.done(),
        "yields": calendar.yields,
    }

    ticker.stop()
    hung.set()
    await hung_task
    tick_task.cancel()
    try:
        await tick_task
    except asyncio.CancelledError:
        pass
    return stats


def _arm_pool(subject: _Subject, values: dict) -> tuple[list[Finding], dict, str]:
    """ARM POOL (§10, §6.4): containment and cooperative yielding, both measured."""
    rig = _rig(subject, values)
    symbols = [f"SYM{i:02d}" for i in range(FLOORS["symbols"])]
    if len(symbols) < FLOORS["symbols"]:
        return (
            [],
            {},
            (
                f"the pool drive runs {len(symbols)} symbol(s), below the floor of "
                f"{FLOORS['symbols']} -- over a tiny population 'yields per symbol' "
                "and 'yields at the edges' are the same number (C.4, §17)"
            ),
        )
    findings: list[Finding] = []
    stats = asyncio.run(_pool_drive(subject, rig, symbols))
    if not stats["margin_hung"]:
        return (
            findings,
            stats,
            (
                "the margin fetch that was supposed to hang forever completed, so "
                "the containment control never held its subject in the state it was "
                "measuring (§17)"
            ),
        )
    if stats["calendar_publishes"] < 1:
        findings.append(
            Finding(
                f"{REL_POLLERS}:CalendarPoller.refresh",
                "the calendar refresh did not complete while a margin fetch was "
                "hung on the same loop. §6.4 puts both on the shared pool (§10) "
                "and `calendar_seam.py` makes poll_once async precisely so 'a "
                "hung broker socket must cost one suspended coroutine and not "
                "one blocked pool worker'",
            )
        )
    floor = FLOORS["symbols"] // 2
    if stats["ticks_during"] < floor:
        findings.append(
            Finding(
                f"{REL_POLLERS}:CalendarPoller.refresh",
                f"a competing task was scheduled {stats['ticks_during']} time(s) "
                f"during a {len(symbols)}-symbol rebuild, below {floor}. "
                "`calendar_seam.py` makes refresh async for DURATION -- "
                "'cooperative yielding during a long rebuild so a slow calendar "
                "refresh cannot starve the fast margin poll sharing the pool' -- "
                "and a coroutine that awaits only at its edges is a blocking "
                "function with `async` written on it",
            )
        )
    return findings, stats, ""


def _arm_publish(subject: _Subject, values: dict) -> tuple[list[Finding], int, str]:
    """ARM PUBLISH (§12.7): synchronous, atomic by rebind, and O(1) to read."""
    rig = _rig(subject, values)
    symbols = [DRIVE_SYMBOL, OTHER_SYMBOL]
    poller, _ = _margin_poller(subject, rig, symbols)
    findings: list[Finding] = []

    rig.clock.set_ms(0.0)
    asyncio.run(poller.poll_once())
    rig.clock.set_ms(1_000.0)
    asyncio.run(poller.poll_once())
    if poller.publishes < FLOORS["publishes"]:
        return (
            findings,
            poller.publishes,
            (
                f"the poller published {poller.publishes} time(s), below the floor "
                f"of {FLOORS['publishes']} -- a cache that never published cannot be "
                "judged on what it published (§17)"
            ),
        )

    # A published snapshot must not be reachable through the caller's list.
    mutable = list(poller.published())
    snapshot = poller.published()
    mutable.clear()
    poller.publish(tuple(snapshot))
    if len(poller.published()) != len(snapshot):
        findings.append(
            Finding(
                f"{REL_POLLERS}:MarginPoller.publish",
                "the published snapshot changed when a caller's own sequence "
                "was mutated -- §12.7's mirror model requires the published "
                "table be the owner's, and a shared mutable object is a second "
                "writer with no name",
            )
        )
    if poller.baseline(DRIVE_SYMBOL) is None:
        findings.append(
            Finding(
                f"{REL_POLLERS}:MarginPoller.baseline",
                f"the O(1) read for {DRIVE_SYMBOL!r} returned None after a "
                "publish that carried it -- the index and the published tuple "
                "disagree, which is the torn state the single rebind exists to "
                "prevent",
            )
        )
    return findings, poller.publishes, ""


def _arm_empty(subject: _Subject, values: dict) -> tuple[list[Finding], str]:
    """ARM EMPTY: EMPTY before first publish, and the cache is as stale as its
    STALEST key."""
    rig = _rig(subject, values)
    symbols = [DRIVE_SYMBOL, OTHER_SYMBOL]
    poller, _ = _margin_poller(subject, rig, symbols)
    seam = subject.seam
    findings: list[Finding] = []

    if poller.state() is not seam.CacheState.EMPTY:
        findings.append(
            Finding(
                f"{REL_POLLERS}:MarginPoller.state",
                f"a cache that has never published reports {poller.state()} "
                "rather than EMPTY. `calendar_seam.py` puts EMPTY first for this "
                "reason: a cache that has never heard from its poller must not "
                "be indistinguishable from a quiet healthy one, because here the "
                "book gets flattened",
            )
        )
    if poller.freshness() is not None:
        findings.append(
            Finding(
                f"{REL_POLLERS}:MarginPoller.freshness",
                "a cache that has never published returned a freshness stamp -- "
                "a stamp for data that does not exist",
            )
        )

    # One symbol kept current, one left to die: the cache is STALE.
    threshold = rig.tracker.policy.threshold_ms(subject.pollers.MARGIN_FEED)
    at0 = rig.clock.set_ms(0.0)
    poller.on_push(_baseline_rows(subject, symbols, at0, 1), at0)
    at1 = rig.clock.set_ms(threshold * 100.0)
    poller.on_push(_baseline_rows(subject, [DRIVE_SYMBOL], at1, 2), at1)
    if poller.state() is not seam.CacheState.STALE:
        findings.append(
            Finding(
                f"{REL_POLLERS}:MarginPoller.state",
                f"one symbol current and one {threshold * 100:.0f} ms dead "
                f"reported {poller.state()} for the cache as a whole. The whole "
                "is as stale as its STALEST key: §6.4b keys the guard per symbol "
                "precisely because one live symbol says nothing about the rest",
            )
        )
    stamp = poller.freshness()
    if stamp is not None and stamp.as_of != at0:
        findings.append(
            Finding(
                f"{REL_POLLERS}:MarginPoller.freshness",
                f"the cache-level freshness reported {stamp.as_of.isoformat()}, "
                "the NEWEST key rather than the oldest. A freshness taken from "
                "the newest key can never go stale while any one symbol is "
                "being updated",
            )
        )
    return findings, ""


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


def _all_arms(
    home: Path, subject: _Subject, values: dict
) -> tuple[list[Finding], dict, str]:
    """Every arm, in order, stopping at the first that cannot measure.

    ARM SHAPE runs first and short-circuits: every behavioural arm below stands
    on it, and driving a poller whose `publish` returns an un-awaited coroutine
    would report an empty cache and hide the defect that produced it.
    """
    findings: list[Finding] = []
    stats: dict = {"arms": 0}

    shape_findings, stats["verbs"], cannot = _arm_shape(subject)
    findings += shape_findings
    if cannot or shape_findings:
        return findings, stats, cannot
    stats["arms"] += 1

    port_findings, stats["ports"], cannot = _arm_ports(subject, values)
    findings += port_findings
    if not cannot:
        stats["arms"] += 1
        lock_findings, cannot = _arm_lock(home, subject, values)
        findings += lock_findings
    if not cannot:
        stats["arms"] += 1
        findings, stats, cannot = _behavioural_arms(subject, values, findings, stats)
    return findings, stats, cannot


def _behavioural_arms(
    subject: _Subject, values: dict, findings: list[Finding], stats: dict
) -> tuple[list[Finding], dict, str]:
    """The five drives. Each stops the sweep the moment it loses its subject."""
    for arm in (_arm_push, _arm_guard, _arm_empty):
        arm_findings, cannot = arm(subject, values)
        findings += arm_findings
        if cannot:
            return findings, stats, cannot
        stats["arms"] += 1

    pool_findings, pool_stats, cannot = _arm_pool(subject, values)
    findings += pool_findings
    stats.update(pool_stats)
    if cannot:
        return findings, stats, cannot
    stats["arms"] += 1

    pub_findings, stats["publishes"], cannot = _arm_publish(subject, values)
    findings += pub_findings
    if cannot:
        return findings, stats, cannot
    stats["arms"] += 1
    return findings, stats, ""


def _pass(stats: dict) -> CheckResult:
    return CheckResult(
        name=NAME,
        status=Status.PASS,
        evidence=(
            f"{stats['arms']} arms over {REL_POLLERS}. SHAPE: {stats['verbs']} "
            "verbs async/sync exactly as calendar_seam.py declared them. "
            f"PORTS: {stats['ports']} "
            "declared (class, Protocol) pairs resolved and isinstance-checked "
            f"against {REL_SEAM}. LOCK: no expression names the live per-symbol "
            "margin field, FinancialPicture is not imported, and every published "
            "row is a §6.3 MarginBaseline -- §6.4's v1.3 refusal of a second "
            "margin table, measured. PUSH: PRIMARY before any push, "
            "FALLBACK_AUDIT with a strictly wider cadence after one, PRIMARY "
            "again on push silence with no event delivered, and an equal audit "
            "interval REFUSED at construction. GUARD: a reading behind a fresher "
            "push is discarded per key and the published baseline does not "
            "regress. POOL: a calendar refresh over "
            f"{FLOORS['symbols']} symbols completed while a margin fetch hung "
            f"forever on the same loop, and a competing task was scheduled "
            f"{stats['ticks_during']} times DURING that rebuild "
            f"({stats['yields']} yields). PUBLISH: {stats['publishes']} atomic "
            "synchronous publishes, snapshot unreachable through the caller's "
            "sequence, O(1) reads consistent. EMPTY: EMPTY before first publish, "
            "stalest key decides the cache. NOT MEASURED HERE: the detector "
            "itself (check_staleness), the transport (check_state_bus), and any "
            "behaviour of a real vendor socket -- `fetch` is injected"
        ),
    )


def _measure(home: Path) -> CheckResult:
    """Everything `run` does, minus the catch-all."""
    absent = _subject_defects(home)
    if absent is not None:
        return absent
    values, error = _config_values(home)
    if error:
        return _cannot(f"{error} (§17)")
    subject, complaint = load_subject(home)
    if subject is None:
        return _cannot(complaint)
    findings, stats, cannot = _all_arms(home, subject, values)
    return _verdict(findings, stats, cannot)


def _verdict(findings: list[Finding], stats: dict, cannot: str) -> CheckResult:
    """The check contract's aggregate ordering, applied WITHIN this check:
    `Fail > Cannot-measure > Guarded > Pass`."""
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
    """Eight arms over §6.4's two pollers, driven on a real event loop."""
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
