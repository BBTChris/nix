#!/usr/bin/env python3
"""Every reservation reaches EXACTLY ONE terminal release, on every path §3 names.

ONE gate, ONE property (`nix_check_contract.md` §5.5): the locked invariant in
`nics_risk_subsystem_spec_v1.3.md` §14 — *"Every reservation reaches exactly one
terminal release"* — holds over `scripts/nixrisk/reservations.py`, driven, for
the whole release-path set §3 names.

**Exactly one is TWO failures.** The gate is built as two arms over one drive
because a single arm can only see one of them:

  * **ARM LEAK (zero releases).** A terminal event that leaves the reservation in
    the TAKEN set. Σ never falls, deployable capital shrinks permanently, and §3
    Phase B eventually denies everything.
  * **ARM DOUBLE (two or more releases).** A second terminal event for the same
    order that decrements Σ again. Committed margin under-counts and Phase B
    approves orders the account cannot carry.

**The second is invisible to a leak test that only checks the ledger drains**,
which is why this gate never asserts "outstanding is empty" on its own: it
asserts the Σ TRAJECTORY and the §11.7 reconcile at each step, plus the count of
Plane-1 `reservation_released` rows per reservation_id.

## HOW THE PATH SET IS OBTAINED, and why it is not the implementation's

**Deriving the path set from the code and then proving the code covers it is
circular and passes while measuring nothing.** The enumeration here comes from
the FROZEN SPEC's own sentence, parsed at run time by
`check_limiter_seam.spec_terminal_paths` — the mechanism that gate already owns
and that this one reuses rather than reimplements. No release path is spelled as
a literal anywhere in this file; `scripts/tests/test_check_reservation_lifecycle.py`
asserts that mechanically, so a member added to the seam or to the ledger cannot
widen what this gate expects.

The complementary direction — an implementation reaching a terminal state the
spec does NOT name — is `check_limiter_seam` ARM 1's, which reddens with
*"FINDING ABOUT THE SPEC"* rather than absorbing it. This gate does not duplicate
that comparison; it consumes its result. A path §3 names for which the seam
declares no member makes this gate CANNOT_MEASURE, naming the path, because the
drive cannot be performed — not PASS over a set it silently shrank.

## ARM SIGMA — §11.3 and §11.7, and why the reconcile would otherwise be furniture

§11.3 keeps Σ reservations as an *incremental running aggregate*; §11.7 reconciles
every running aggregate against a full scan. If `total_reserved()` were computed
FROM the store, the two sides of that reconcile would be the same arithmetic over
the same data and drift would be 0.0 over any defect at all. This gate therefore
also reads the ledger's `total_reserved` STATICALLY and reddens if it scans, and
it refuses a module whose own audit tolerance is wider than the gate's or whose
minimum admissible margin sits within a thousandfold of that tolerance — a double
release inside the noise floor is a double release nobody can see.

## debug.md §7.12 — THE STANDING QUESTION, answered at the point the gate is built

*What would have to be true for this gate to PASS while measuring nothing?*

1. **The path set could be empty or tiny.** A spec sentence that moved leaves an
   empty expected set that agrees with anything. *Closed:* `MIN_TERMINAL_PATHS`
   is a floor, not today's count, and an unparsable sentence is CANNOT_MEASURE.
2. **The margins could be zero.** Every Σ assertion becomes `0 == 0` and both
   arms are vacuous. *Closed:* the drive asserts Σ rose by the exact fsum of the
   proposed margins before any release is attempted, and the ledger itself
   refuses a margin below `MIN_MARGIN`.
3. **The gate could construct the release calls and then assert they happened.**
   That measures the gate, not the ledger. *Closed:* the gate calls `resolve`
   with a terminal EVENT and never touches the ledger's stores; every verdict is
   read back from `total_reserved()`, `outstanding()`, `audit()` and the Plane-1
   row stream, all of which the ledger maintains itself.
4. **The tolerance could swallow the defect.** *Closed:* `GATE_TOLERANCE` is
   fixed here, the module's own tolerance must not exceed it, and the module's
   minimum margin must exceed it by `SEPARATION_FACTOR`.
5. **The subject could be absent.** *Closed:* an unimportable ledger is
   CANNOT_MEASURE naming the import error, never a PASS (§17, §5.3).

## WHAT THIS GATE CANNOT PROVE, stated rather than implied

It drives the LEDGER. It does not prove that the Limiter's event handlers call
`resolve` on every real fill, cancel, reject, pending-timeout and blackout onset,
because THREE of those handlers now exist while THREE of §3's release paths still
have no production caller at all — D3.358 names which three, measured ARC 038/B,
and this file deliberately does not, for the reason the section above gives: a
path spelled here as a literal would make the expected side a constant this gate
chose. When ARC 028 wrote this paragraph none of the handlers existed and the
residual was total; it is now partial, and a green here still does not mean the
system releases on every path. Out of scope then and still out of scope now —
stop conversion, protective-exit
wiring, session-close flatten, HALT semantics, cold-start reconciliation, the
Sentinel, Scoring and the Allocator are all outside ARC 028. A green here means
*the ledger has no leak path and absorbs no double release across §3's path set*.
It does NOT mean the system releases on every path in production, and §13's
objective 23 (the reservation-leak property test across all failure paths) stays
open. CHECK-DEBT D3.51.
"""

from __future__ import annotations

import ast
import dataclasses
import importlib
import inspect
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, NamedTuple

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order

# `check_limiter_seam` is imported as a SIBLING, which `loader.py` supports by
# design ("a top-level `import _sibling` inside it resolves the same way it would
# if the check were run standalone"). It is imported for its spec PARSER only —
# not for its verdict — so this is not a DEPENDS_ON ordering relationship: the
# two gates read the same frozen file and neither produces state the other reads.
import check_limiter_seam as seam_gate  # pylint: disable=wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

# pylint: disable=duplicate-code
# The wiring census adds three small value classes and one wide drive to a
# module that was already at the house line ceiling. Split-for-the-linter
# would put the census and the drive it feeds in two files that must be read
# together, which is the cost this file's own docstring argues against.
# pylint: disable=too-many-lines,too-few-public-methods
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

#: Nothing must run first. The spec is a file on disk; the ledger is imported
#: from the tree under test; no check produces either.
DEPENDS_ON: tuple[str, ...] = ()
#: This gate IMPORTS the ledger package out of `ctx.nix_home`, so it mutates
#: `sys.path` and `sys.modules` for the duration of the load and restores both.
#: Declared for the same reason `check_datafeed_bar_seal` declares them: two
#: checks doing this concurrently share one interpreter's import state.
RESOURCES: tuple[str, ...] = ("interpreter:sys.modules", "interpreter:sys.path")
#: No timeout, no poll, no sleep. The drive is arithmetic over dictionaries.
TIME_BOUND = False
#: NON-CORRECTABLE. The defects this gate finds are a leaked reservation and an
#: absorbed double release — money-correctness defects in the Limiter's ledger.
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the repair for a leaked reservation or an absorbed double release is a "
    "change to the Limiter's money arithmetic, decided by a human against the "
    "frozen spec. An instrument empowered to edit the ledger until its own drive "
    "came back clean would be manufacturing its own green over the one invariant "
    "(§14) that stops the system over-committing real capital"
)
#: Genuinely MEASURED here: the ledger is imported and driven, and its source is
#: parsed. The seam is READ (its types are constructed to drive the ledger) and
#: is declared by check_limiter_seam, which is where its own gate lives.
SUBJECTS: tuple[str, ...] = (
    "scripts/nixrisk/reservations.py",
    #: ARC 044. ARM WIRING drives the real `OrderOutcomes` — the production
    #: release site for §3's non-fill terminal paths — so this file is measured
    #: here, not merely read. Which paths those are is DERIVED (see ARM WIRING);
    #: naming them here would put the expected set in this gate's own source,
    #: which is the circularity B2 names and which this gate's own test greps
    #: for.
    "scripts/nixrisk/outcomes.py",
)

NAME = "check_reservation_lifecycle"

LEDGER = "scripts/nixrisk/reservations.py"
PACKAGE = "nixrisk"
MODULE = "nixrisk.reservations"
SEAM_MODULE = "nixrisk.seam"
OUTCOMES = "scripts/nixrisk/outcomes.py"
OUTCOMES_MODULE = "nixrisk.outcomes"
#: Where ARM WIRING censuses production release sites. Every non-test module in
#: the Limiter's package, by SHAPE — never a hand-list of filenames.
NIXRISK_DIR = ("scripts", "nixrisk")

#: Non-vacuity floor on the SPEC side (`debug.md` §7.12 answer 1). A floor, never
#: today's count — a threshold equal to the current number reddens the moment the
#: spec is amended and proves nothing in the meantime.
MIN_TERMINAL_PATHS = 3

#: What one path's drive books. Three distinct, non-round, strictly positive
#: margins: one is released under test, one is the double-release subject, and
#: the rest must drain — a single-reservation drive cannot tell "the ledger
#: released the right one" from "the ledger emptied itself".
_ORDERS: tuple[tuple[int, float], ...] = ((3, 1234.5), (1, 2345.75), (2, 987.25))

#: The bucket an unreadable `via` lands in. Its non-emptiness is CANNOT_MEASURE:
#: an enumeration with a hole in it has not enumerated anything.
UNREADABLE = "<unresolved>"

#: The marker `_wiring_structure` returns instead of a census when the tree under
#: test is not a whole package. Not a release-path member, so it can never be
#: confused with one.
ABSTAINED = "<abstained>"

#: Non-vacuity floor on ARM WIRING's own subject. The wiring census is a
#: statement about a WHOLE Limiter package; a plant harness stages a handful of
#: files on a `tmp_path` (doctrine C.8), and over such a tree "no module books
#: this path" is true and means nothing. Below this floor the arm ABSTAINS and
#: says so — it neither reports a leak it cannot have observed, nor turns
#: another arm's real finding into CANNOT_MEASURE. A FLOOR, never today's count:
#: the shipped package holds far more, so it reddens nothing real, and an
#: equality against the current number would move every time a module lands.
MIN_CENSUS_MODULES = 8

#: §11.7's drift floor, owned HERE so the subject cannot widen its way to green.
GATE_TOLERANCE = 1e-9
#: How far the smallest admissible reservation must sit above that floor. Below
#: this separation a double release of a minimum-margin reservation lands inside
#: the noise and the SIGMA arm stops discriminating.
SEPARATION_FACTOR = 1000.0


class Finding(NamedTuple):
    """One defect: where it is, and what is wrong. Never a bare status."""

    site: str
    why: str


class Loaded(NamedTuple):
    """The ledger, the seam, and the non-fill outcome handlers, from the tree."""

    reservations: ModuleType
    seam: ModuleType
    #: `nixrisk.outcomes` — the production release site for §3's three non-fill
    #: paths (ARC 044). OPTIONAL because a tree that does not have it must be
    #: CANNOT_MEASURE over ARM WIRING's driven half rather than crash, and never
    #: a PASS (§17). Its ABSENCE is separately a FAIL on the structural half,
    #: because §3's paths then have no production release site at all.
    outcomes: ModuleType | None = None


@dataclasses.dataclass
class Tally:
    """What the drive actually did. Non-vacuity is read off this, not asserted."""

    reservations: int = 0
    releases: int = 0
    refusals: int = 0
    plane1_rows: int = 0
    margin: float = 0.0
    paths: list[str] = dataclasses.field(default_factory=list)


class Recorder:
    """A Plane-1 sink that keeps every row (§9's `enqueue`, no durability).

    Duck-typed rather than imported: the seam this gate constructs against comes
    out of `ctx.nix_home`, so a nominal `Plane1Port` from THIS process would be a
    different class object than the one the loaded ledger sees.
    """

    def __init__(self) -> None:
        self.rows: list[Any] = []

    def enqueue(self, row: Any) -> None:
        """Append. Bounded by the drive, which books nine rows per path."""
        self.rows.append(row)

    def sync_to_disk(self) -> int:
        """Nothing is made durable here; the drive reads `rows` directly."""
        return 0

    def pending(self) -> int:
        """Every row is pending — this sink never syncs."""
        return len(self.rows)

    def released_for(self, reservation_id: str) -> int:
        """How many `reservation_released` rows name this reservation_id."""
        named = [
            row
            for row in self.rows
            if getattr(row, "kind", None) is not None
            and str(getattr(row.kind, "value", "")).endswith("_released")
            and dict(getattr(row, "fields", {})).get("reservation_id") == reservation_id
        ]
        return len(named)


def _cannot_measure(detail: str) -> CheckResult:
    return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=detail)


# --------------------------------------------------------------------------
# LOADING — the ledger comes out of the tree under test, never out of this one
# --------------------------------------------------------------------------


def _purge(saved: dict[str, ModuleType]) -> None:
    """Drop every `nixrisk*` module, restoring whatever was there before."""
    for name in [
        key for key in sys.modules if key == PACKAGE or key.startswith(f"{PACKAGE}.")
    ]:
        del sys.modules[name]
    sys.modules.update(saved)


def load(home: Path) -> tuple[Loaded | None, str]:
    """Import the ledger from `home`, leaving the interpreter as it was found.

    A path-keyed import is what lets a plant live on a `tmp_path` COPY (doctrine
    C.8): the gate drives whichever tree it is pointed at, and the production
    ledger is never written.
    """
    saved_path = list(sys.path)
    saved_modules = {
        key: value
        for key, value in sys.modules.items()
        if key == PACKAGE or key.startswith(f"{PACKAGE}.")
    }
    _purge({})
    sys.path.insert(0, str((home / "scripts").resolve()))
    # A tree created after interpreter start is invisible to FileFinder's
    # directory-mtime cache, and the resulting ModuleNotFoundError would be
    # reported as "the subject is unavailable" over a subject that is right
    # there. Required, not defensive: every plant lives in a fresh tmp_path.
    importlib.invalidate_caches()
    try:
        try:
            outcomes: ModuleType | None = importlib.import_module(OUTCOMES_MODULE)
        except Exception:  # pylint: disable=broad-except  # noqa: BLE001
            # Absence is a MEASUREMENT, not an error: ARM WIRING's structural
            # half reports the missing release sites and its driven half says
            # it could not run. Swallowing it here would hide the finding.
            outcomes = None
        loaded = Loaded(
            reservations=importlib.import_module(MODULE),
            seam=importlib.import_module(SEAM_MODULE),
            outcomes=outcomes,
        )
        return loaded, ""
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return None, (
            f"{LEDGER}: cannot import {MODULE} from {home} — "
            f"{type(exc).__name__}: {exc}. The subject is unavailable, so "
            "nothing was measured (§17: never a PASS)"
        )
    finally:
        sys.path[:] = saved_path
        _purge(saved_modules)


def spec_paths(home: Path) -> tuple[tuple[str, ...], str]:
    """§3's release paths, PARSED FROM THE FROZEN SPEC — never from the ledger."""
    parsed, complaint = seam_gate.spec_terminal_paths(home)
    if complaint:
        return (), complaint
    if len(parsed) < MIN_TERMINAL_PATHS:
        return (), (
            f"§3 yielded only {len(parsed)} release path(s) "
            f"({', '.join(sorted(parsed)) or 'none'}), below the floor of "
            f"{MIN_TERMINAL_PATHS} — the parse stopped matching, and an empty "
            "expected set would compare green against any ledger at all"
        )
    return tuple(sorted(parsed)), ""


def _members(loaded: Loaded, names: tuple[str, ...]) -> tuple[dict[str, Any], str]:
    """Resolve each spec-named path to the seam's enum member, or say which one."""
    resolved: dict[str, Any] = {}
    for name in names:
        member = getattr(loaded.seam.TerminalPath, name, None)
        if member is None:
            return {}, (
                f"§3 names release path {name} and the seam declares no such "
                "TerminalPath member, so that path cannot be driven. That "
                "disagreement is check_limiter_seam's property; this gate "
                "refuses to report over a set it silently shrank"
            )
        resolved[name] = member
    return resolved, ""


# --------------------------------------------------------------------------
# THE DRIVE
# --------------------------------------------------------------------------


def _orders(loaded: Loaded, tag: str) -> tuple[Any, ...]:
    """Three proposals with distinct, non-round, strictly positive margins."""
    seam = loaded.seam
    return tuple(
        seam.ProposedOrder(
            client_order_id=f"{tag}-{index}",
            strategy_id=f"strat-{tag}",
            symbol="ESZ6",
            side=seam.Side.LONG,
            qty=qty,
            margin_per_contract=per_contract,
            stop_ticks=20,
            stop_mode=seam.StopMode.FIXED,
            signal_ts=1000.0 + index,
        )
        for index, (qty, per_contract) in enumerate(_ORDERS)
    )


def _non_vacuity(ledger: Any, orders: tuple[Any, ...], path: str) -> list[Finding]:
    """Σ must have RISEN by the exact booked figure before anything is released."""
    booked = sum(order.proposed_margin for order in orders)
    sigma = ledger.total_reserved()
    site = f"{LEDGER}:take[{path}]"
    if booked <= 0.0:
        return [
            Finding(
                site,
                f"the drive booked {booked!r} of margin — every Σ "
                "assertion below would be 0 == 0",
            )
        ]
    if abs(sigma - booked) > GATE_TOLERANCE:
        return [
            Finding(
                site,
                f"Σ reads {sigma!r} after taking {len(orders)} reservations "
                f"worth {booked!r} — the running aggregate did not follow the "
                "takes, so no later Σ reading means anything",
            )
        ]
    if len(ledger.outstanding()) != len(orders):
        return [
            Finding(
                site,
                f"{len(ledger.outstanding())} of {len(orders)} reservations are "
                "outstanding after the takes — the TAKEN set is not the ground "
                "truth Σ is derived from",
            )
        ]
    return []


def _arm_leak(
    ledger: Any, rec: Recorder, order: Any, member: Any, path: str
) -> tuple[list[Finding], Any]:
    """ZERO releases: the terminal event fires and the reservation stays TAKEN."""
    site = f"{LEDGER}:resolve[{path}]"
    before = ledger.total_reserved()
    resolution = ledger.resolve(order.client_order_id, member, 2000.0)
    if not resolution.accepted:
        why = getattr(resolution.refusal, "reason", "no reason given")
        return [
            Finding(
                site,
                f"§3 names {path} as a release path and the ledger did not "
                f"release on it: {why} — §3's 'No leak paths' is a statement "
                "about the whole path set, and this path is a leak",
            )
        ], None
    released = resolution.released
    findings: list[Finding] = []
    if getattr(released.released_via, "name", "") != path:
        findings.append(
            Finding(site, f"released via {released.released_via!r}, not {path}")
        )
    fell = before - ledger.total_reserved()
    if abs(fell - order.proposed_margin) > GATE_TOLERANCE:
        findings.append(
            Finding(
                site,
                f"a release via {path} moved Σ by {fell!r}, not by the reserved "
                f"{order.proposed_margin!r} — a LEAK: the reservation reports "
                "released while its capital stays committed",
            )
        )
    if any(
        res.reservation_id == released.reservation_id for res in ledger.outstanding()
    ):
        findings.append(
            Finding(
                site,
                f"{released.reservation_id} is still in the TAKEN set after a "
                f"release via {path} — a LEAK that permanently reduces "
                "deployable capital",
            )
        )
    findings += _rows_arm(rec, released.reservation_id, 1, site)
    findings += _audit_arm(ledger, site, path)
    return findings, released


def _arm_double(
    ledger: Any,
    rec: Recorder,
    released: Any,
    other: Any,
    path: str,
) -> list[Finding]:
    """TWO releases: the §4 remainder-cancel that arrives after the fill release."""
    site = f"{LEDGER}:resolve[{path}+duplicate]"
    before = ledger.total_reserved()
    resolution = ledger.resolve(released.client_order_id, other, 3000.0)
    findings: list[Finding] = []
    if resolution.accepted:
        findings.append(
            Finding(
                site,
                f"a SECOND terminal event for {released.reservation_id} (already "
                f"released via {path}) was ACCEPTED — §14 requires exactly one "
                "terminal release, and a second decrement under-counts committed "
                "margin, which lets §3 Phase B over-commit. This is invisible to "
                "a leak test: the ledger still drains to empty",
            )
        )
    else:
        findings += _refusal_arm(resolution.refusal, released, path, site)
    after = ledger.total_reserved()
    if after != before:
        findings.append(
            Finding(
                site,
                f"Σ moved from {before!r} to {after!r} on a duplicate terminal "
                f"event for {released.reservation_id} — a DOUBLE RELEASE",
            )
        )
    findings += _rows_arm(rec, released.reservation_id, 1, site)
    findings += _audit_arm(ledger, site, path)
    findings += _port_arm(ledger, released, other, path, site)
    return findings


def _refusal_arm(refusal: Any, released: Any, path: str, site: str) -> list[Finding]:
    """The refusal must NAME the path already taken (check contract v2 §11)."""
    findings: list[Finding] = []
    if getattr(getattr(refusal, "kind", None), "value", "") != "already_terminal":
        findings.append(
            Finding(
                site,
                f"the duplicate terminal event was refused as "
                f"{getattr(refusal, 'kind', None)!r} rather than as an "
                "already-terminal reservation — a ledger whose take and resolve "
                "key on different things refuses everything and leaks everything",
            )
        )
    if getattr(getattr(refusal, "already_via", None), "name", "") != path:
        findings.append(
            Finding(
                site,
                f"the refusal does not name {path} as the path "
                f"{released.reservation_id} already took; it says "
                f"{getattr(refusal, 'already_via', None)!r}. A control that "
                "cannot say WHY has not discriminated",
            )
        )
    return findings


def _port_arm(
    ledger: Any, released: Any, other: Any, path: str, site: str
) -> list[Finding]:
    """The FROZEN port declares `release` RAISES on a double release."""
    try:
        ledger.release(released.reservation_id, other, 4000.0)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        if path.lower() not in str(exc).lower():
            return [
                Finding(
                    site,
                    f"release() refused the second call with "
                    f"{type(exc).__name__}: {exc} — which does not name {path}, "
                    "the path already taken. The exception TYPE is a shared "
                    "namespace; the reason is the evidence",
                )
            ]
        return []
    return [
        Finding(
            site,
            f"release({released.reservation_id}, {other!r}) RETURNED after that "
            f"reservation was already released via {path}. The frozen "
            "ReservationLedgerPort declares it 'Raises on unknown id and on "
            "double release'",
        )
    ]


def _rows_arm(
    rec: Recorder, reservation_id: str, expected: int, site: str
) -> list[Finding]:
    """§12.10 books `reservation released` on Plane 1 — once, never twice."""
    seen = rec.released_for(reservation_id)
    if seen == expected:
        return []
    return [
        Finding(
            site,
            f"Plane 1 carries {seen} reservation_released row(s) for "
            f"{reservation_id}, expected {expected} — §12.10 makes that row the "
            "auditable record of the release, so a count that disagrees with the "
            "ledger's own books means the money truth and its record diverged",
        )
    ]


def _audit_arm(ledger: Any, site: str, path: str) -> list[Finding]:
    """§11.7: the incremental Σ must reconcile against a full scan."""
    audit = ledger.audit()
    if not audit.material and abs(audit.drift) <= GATE_TOLERANCE:
        return []
    return [
        Finding(
            site,
            f"§11.7 reconcile after {path}: incremental Σ {audit.aggregate!r} vs "
            f"full scan {audit.scanned!r}, drift {audit.drift!r} — the running "
            "aggregate and ground truth disagree",
        )
    ]


def _arm_drain(
    ledger: Any, rec: Recorder, orders: tuple[Any, ...], member: Any, path: str
) -> list[Finding]:
    """The rest of the population must reach the same terminal path and clear Σ."""
    site = f"{LEDGER}:drain[{path}]"
    findings: list[Finding] = []
    for index, order in enumerate(orders):
        resolution = ledger.resolve(order.client_order_id, member, 5000.0 + index)
        if not resolution.accepted:
            findings.append(
                Finding(
                    site,
                    f"{order.client_order_id} did not release via {path}: "
                    f"{getattr(resolution.refusal, 'reason', '?')}",
                )
            )
            continue
        findings += _rows_arm(rec, resolution.released.reservation_id, 1, site)
    sigma = ledger.total_reserved()
    if abs(sigma) > GATE_TOLERANCE:
        findings.append(
            Finding(
                site,
                f"Σ is {sigma!r} with every reservation released — "
                f"{'a LEAK' if sigma > 0 else 'a DOUBLE RELEASE'}",
            )
        )
    if ledger.outstanding():
        findings.append(
            Finding(
                site,
                f"{len(ledger.outstanding())} reservation(s) still TAKEN after "
                f"every order reached {path}",
            )
        )
    return findings + _audit_arm(ledger, site, path)


def _drive_one(loaded: Loaded, path: str, member: Any, other: Any, tally: Tally):
    """One release path, end to end, on a ledger of its own."""
    rec = Recorder()
    ledger = loaded.reservations.ReservationLedger(rec)
    orders = _orders(loaded, path.lower())
    for order in orders:
        ledger.take(order, 1000.0)
        tally.reservations += 1
        tally.margin += order.proposed_margin
    findings = _non_vacuity(ledger, orders, path)
    if findings:
        return findings
    leak, released = _arm_leak(ledger, rec, orders[0], member, path)
    findings += leak
    if released is not None:
        findings += _arm_double(ledger, rec, released, other, path)
    findings += _arm_drain(ledger, rec, orders[1:], member, path)
    tally.paths.append(path)
    tally.releases += len(ledger.released())
    tally.refusals += len(ledger.refusals())
    tally.plane1_rows += len(rec.rows)
    return findings


def drive(loaded: Loaded, members: dict[str, Any], tally: Tally) -> list[Finding]:
    """Drive every spec-named path. A raising ledger is a FINDING, not a crash."""
    findings: list[Finding] = []
    names = sorted(members)
    for index, path in enumerate(names):
        other = members[names[(index + 1) % len(names)]]
        try:
            findings += _drive_one(loaded, path, members[path], other, tally)
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            findings.append(
                Finding(
                    f"{LEDGER}:[{path}]",
                    f"the drive raised {type(exc).__name__}: {exc} — the ledger "
                    "refused a path §3 names, which is a leak by another route",
                )
            )
    return findings


# --------------------------------------------------------------------------
# ARM SIGMA — §11.3's aggregate must be incremental, and the floors must separate
# --------------------------------------------------------------------------


def _returns_stored_attribute(node: ast.FunctionDef) -> str:
    """`""` when the body is a bare `return self.<attr>`; else what it does."""
    body = [
        stmt
        for stmt in node.body
        if not (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant))
    ]
    if len(body) != 1 or not isinstance(body[0], ast.Return):
        return f"{len(body)} statement(s), not a single return"
    value = body[0].value
    if isinstance(value, ast.Attribute):
        return ""
    return f"returns a {type(value).__name__}, not a stored attribute"


def arm_sigma(home: Path, module: ModuleType) -> list[Finding]:
    """§11.3 incremental, and §11.7's reconcile kept non-vacuous by construction."""
    findings: list[Finding] = []
    tree = ast.parse((home / LEDGER).read_text(encoding="utf-8"), filename=LEDGER)
    found = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "total_reserved"
    ]
    site = f"{LEDGER}:total_reserved"
    if not found:
        findings.append(Finding(site, "the ledger declares no total_reserved"))
    for node in found:
        why = _returns_stored_attribute(node)
        if why:
            findings.append(
                Finding(
                    f"{site}:{node.lineno}",
                    f"{why} — §11.3 requires an incremental running aggregate, "
                    "and a Σ computed FROM the store cannot disagree with a full "
                    "scan OF that store, so §11.7's reconcile would compare a "
                    "value with itself and report drift 0.0 over any defect",
                )
            )
    return findings + _arm_floors(module)


def _arm_floors(module: ModuleType) -> list[Finding]:
    """The module may not widen its way past this gate's discrimination floor."""
    findings: list[Finding] = []
    tolerance = float(getattr(module, "AUDIT_TOLERANCE", GATE_TOLERANCE))
    minimum = float(getattr(module, "MIN_MARGIN", 0.0))
    if tolerance > GATE_TOLERANCE:
        findings.append(
            Finding(
                f"{LEDGER}:AUDIT_TOLERANCE",
                f"{tolerance!r} is wider than this gate's {GATE_TOLERANCE!r} — a "
                "subject that sets its own drift floor can absorb a real double "
                "release and still report material=False",
            )
        )
    if minimum < GATE_TOLERANCE * SEPARATION_FACTOR:
        findings.append(
            Finding(
                f"{LEDGER}:MIN_MARGIN",
                f"{minimum!r} is not {SEPARATION_FACTOR!r}x above the drift floor "
                f"{GATE_TOLERANCE!r} — a double release of a minimum-margin "
                "reservation would sit inside the noise and this gate's Σ arm "
                "would stop discriminating",
            )
        )
    return findings


# --------------------------------------------------------------------------
# ARM WIRING — §14 needs a release on every path §3 names, IN PRODUCTION
# --------------------------------------------------------------------------
#
# The arms above drive the LEDGER, which has always been able to release on
# every path §3 names — so they are green over a tree in which NOTHING CALLS IT.
# ARC 038 (F-B3, CHECK-DEBT D3.358) measured that exact state: three of the six
# paths had a production release site and three had none, so a rejected,
# timed-out or fully-cancelled entry held its whole reservation for the life of
# the process while §11.7's reconcile reported `drift=0.0` over it — a leak
# breaks no arithmetic identity and the full-scan reconcile is structurally
# blind to one.
#
# NOT ONE RELEASE PATH IS NAMED IN THIS FILE, and that is mechanical, not
# stylistic: `test_the_PATH_SET_is_PARSED_FROM_THE_SPEC_and_appears_NOWHERE_in_
# the_gate` greps this source for every member the spec parse yields. An
# expected set the gate typed would make the gate prove the ledger covers a set
# the gate chose. So the EXPECTED side comes from the frozen spec, the OBSERVED
# side from an AST census of the tree, and the DRIVEN side from the intersection
# of the census with the handler module's own published verb map — three
# derivations, no list.
#
# Three halves, failing three different ways:
#
#   STRUCTURAL — census every production release site BY SHAPE (an AST walk for
#   a `resolve`/`release` call, plus a STATIC read of its `via` argument) and
#   require one for every path the FROZEN SPEC names. A spec path with no site
#   is a FAIL naming that path and the leak it implies. Derivation, not a list:
#   a seventh path added to §3 arrives already measured, and a new module that
#   books one is credited the moment it lands.
#
#   LIVENESS / COMPLETENESS — a release call whose `via` cannot be read
#   statically is reported by the census as unreadable, and this arm then
#   answers CANNOT_MEASURE (exit 2) NAMING THE SITE. That is the whole
#   anti-blindness argument (`debug.md` §7.12; the D3.440 drill-vs-daemon
#   lesson): a terminal-transition site the enumeration cannot name might be a
#   path that leaks, and a gate that cannot enumerate its subject has not
#   measured it. A hand-list would have ignored the same site in silence.
#
#   DRIVEN — the paths the handler module books are then driven through its REAL
#   public verbs against the REAL ledger. Σ must return to its pre-reservation
#   value, exactly once per reservation (a leak leaves it INFLATED), and a
#   SECOND terminal event for the same order must leave Σ BIT-identical (an
#   absorbed double release leaves it UNDER-counted, which is §15 C1's
#   cap-breach direction). The paths booked by the fill and flatten modules are
#   proven WIRED here and driven by `check_fill_handler` and `check_flatten`,
#   which declare those files as their own SUBJECTS — a second drive here would
#   be the duplicate instrument doctrine C.9 forbids.


def _via_argument(node: ast.Call) -> ast.expr | None:
    """The `via` argument of a `resolve`/`release` call, or `None` if not one."""
    func = node.func
    if not isinstance(func, ast.Attribute):
        return None
    if func.attr not in ("resolve", "release") or len(node.args) < 2:
        return None
    return node.args[1]


def _literal_member(via: ast.expr) -> str | None:
    """A `TerminalPath` member spelled literally at the call site, or `None`."""
    if (
        isinstance(via, ast.Attribute)
        and isinstance(via.value, ast.Name)
        and via.value.id == PATH_ENUM
    ):
        return via.attr
    return None


def _guarded_members(tree: ast.Module) -> list[str]:
    """Members a NON-literal `via` can carry, when a frozenset constrains it.

    A module may take its cause as a parameter and REFUSE anything outside a
    module-level frozenset of enum members before calling `resolve`. That call
    is readable even though its argument is a name, so those members — and only
    those — are credited to it. The rule is written over the SHAPE, never over a
    filename, so any module adopting the same guard is read the same way, and a
    module with no such guard gets nothing from here: its non-literal call lands
    in the unreadable bucket, which is the conservative direction.
    """
    guarded: set[str] = set()
    # MODULE LEVEL ONLY. A frozenset built inside a function is not a guard the
    # census can rely on — it may be rebound, and a call site credited by a
    # local literal would be crediting the reader's optimism. `tree.body`,
    # rather than `ast.walk`, is what makes that constraint mechanical.
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        guarded.update(_frozenset_members(node.value))
    return sorted(guarded)


def _frozenset_members(value: ast.expr | None) -> list[str]:
    """The enum members of a `frozenset({A, B})` literal, or nothing."""
    if not isinstance(value, ast.Call):
        return []
    if not (isinstance(value.func, ast.Name) and value.func.id == "frozenset"):
        return []
    found: list[str] = []
    for arg in value.args:
        if not isinstance(arg, (ast.Set, ast.List, ast.Tuple)):
            continue
        members = [_literal_member(element) for element in arg.elts]
        if members and all(member is not None for member in members):
            found.extend(member for member in members if member is not None)
    return found


def _sites_in(path: Path, found: dict[str, list[str]]) -> None:
    """Add one module's release call sites to `found`, in place."""
    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    guarded = _guarded_members(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        via = _via_argument(node)
        if via is None:
            continue
        site = f"{path.name}:{node.lineno}"
        member = _literal_member(via)
        if member is not None:
            found.setdefault(member, []).append(site)
        elif guarded:
            for cause in guarded:
                found.setdefault(cause, []).append(site)
        else:
            found.setdefault(UNREADABLE, []).append(site)


def release_sites(home: Path) -> dict[str, list[str]]:
    """Release path -> production `resolve`/`release` call sites, by SHAPE.

    Derived over every module in the Limiter's package. Tests live outside that
    package and so cannot inflate the census; nothing is filtered by name, so
    nothing has to be maintained when a module is added.
    """
    root = home.joinpath(*NIXRISK_DIR)
    found: dict[str, list[str]] = {}
    for path in sorted(root.glob("*.py")):
        _sites_in(path, found)
    return found


def _wiring_structure(
    home: Path, paths: tuple[str, ...]
) -> tuple[list[Finding], str, dict[str, list[str]]]:
    """Census + the structural verdicts. Returns (findings, blind, sites)."""
    population = len(list(home.joinpath(*NIXRISK_DIR).glob("*.py")))
    if population < MIN_CENSUS_MODULES:
        return (
            [],
            "",
            {ABSTAINED: [f"{population} module(s) < floor {MIN_CENSUS_MODULES}"]},
        )
    try:
        sites = release_sites(home)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return (
            [],
            (
                f"{OUTCOMES}: the production release-site census could not be "
                f"taken — {type(exc).__name__}: {exc}. Nothing was measured "
                "about which §3 paths production books (§17: never a PASS)"
            ),
            {},
        )
    unreadable = sites.get(UNREADABLE, [])
    if unreadable:
        return (
            [],
            (
                f"a terminal-transition site this gate cannot name: "
                f"{', '.join(sorted(unreadable))} — its `via` argument is "
                f"neither a literal {PATH_ENUM} member nor constrained by a "
                "module-level frozenset of them, so the census cannot say WHICH "
                "release path it books. It may be a path that leaks and this "
                "gate would not see it, so the enumeration is INCOMPLETE and "
                "the verdict is unmeasured rather than green "
                "(nix_check_contract.md §17; debug.md §7.12)"
            ),
            sites,
        )
    findings: list[Finding] = []
    for member in paths:
        if not sites.get(member):
            findings.append(
                Finding(
                    f"{OUTCOMES}:wiring[{member}]",
                    f"§3 names {member} as a release path and NO module in "
                    f"{'/'.join(NIXRISK_DIR)} books it — an order reaching that "
                    f"terminal state holds its whole reservation forever, Σ "
                    f"reservations never falls, committed margin is permanently "
                    f"INFLATED, and §11.7 reports drift 0.0 over it because a "
                    f"leak breaks no arithmetic identity. Production books "
                    f"{dict(sorted(sites.items()))}",
                )
            )
    return findings, "", sites


@dataclasses.dataclass
class WiringTally:
    """What the PRODUCTION drive did. Kept apart from the ledger drive's tally.

    Separate on purpose: the ledger tally's figures are asserted against the
    roster size by this gate's own test (three reservations per spec path), and
    folding a second, differently-shaped drive into it would make that relation
    a coincidence.
    """

    reservations: int = 0
    releases: int = 0
    refusals: int = 0
    margin: float = 0.0
    paths: list[str] = dataclasses.field(default_factory=list)


class _WiringClock:
    """A monotone clock the drive advances itself. Never `time.time`."""

    def __init__(self, start: float) -> None:
        self._now = float(start)

    def __call__(self) -> float:
        self._now += 1.0
        return self._now


class _WiringStatus:
    """What a §4 status query answered. Structural, not imported (§2A inv. 2)."""

    def __init__(self, state: str) -> None:
        self.state = state
        self.terminal = True
        self.client_order_id = ""
        self.cumulative_qty = 0

    def query_order_status(self, client_order_id: str) -> _WiringStatus:
        """§4's status query, answered with the state the drive chose."""
        self.client_order_id = client_order_id
        return self


#: What a status query must answer for a pending order to be DEAD. Read off the
#: handler module's own declared set rather than typed here — see `_fire`.
DEAD_STATE_ATTR = "DEAD_STATES"
#: The handler module's published map of release path -> public verb.
HANDLES_ATTR = "HANDLES"
#: The name the release-path enumeration is bound to at a call site.
PATH_ENUM = "TerminalPath"


def _fire(handler: Any, verb: str, client_order_id: str, module: Any) -> Any:
    """Drive ONE public verb, choosing its call shape from its own signature.

    Two shapes exist and the signature tells them apart without this gate
    knowing which path is which: a PUSH verb takes the order's identifier, and
    the PULL verb (§4's timeout resolution, which resolves by QUERYING and never
    by resending) takes a status-query port. Anything else is unknown to this
    gate and is reported as such rather than guessed at.
    """
    method = getattr(handler, verb)
    params = list(inspect.signature(method).parameters)
    if params and params[0] == "client_order_id":
        return method(client_order_id)
    if params and params[0] == "query":
        dead = sorted(getattr(module, DEAD_STATE_ATTR))
        if not dead:
            raise RuntimeError(f"{OUTCOMES}: {DEAD_STATE_ATTR} is empty")
        return method(_WiringStatus(dead[0]))
    raise RuntimeError(
        f"{OUTCOMES}: {verb}{tuple(params)} is a call shape this gate does not "
        "know how to drive"
    )


def _drive_one_path(  # pylint: disable=too-many-locals
    loaded: Loaded, member: str, verb: str, index: int, tally: WiringTally
) -> tuple[list[Finding], str]:
    """One path: take a real reservation, end it once, then end it again.

    Split out of the loop below because a single function holding both the
    per-path arithmetic and the enumeration around it was over this tree's
    cognitive-complexity ceiling — and because the three verdicts here (leak,
    double release, record mismatch) each want to read as one thought.
    """
    module = loaded.outcomes
    if module is None:  # pragma: no cover - the caller refuses this first
        return [], (
            f"{OUTCOMES}: the non-fill outcome handler is not importable, so "
            f"{member} could not be driven (§17: never a PASS)"
        )
    seam = loaded.seam
    path = getattr(seam.TerminalPath, member, None)
    if path is None:
        return [], (
            f"{OUTCOMES}: the seam declares no {PATH_ENUM}.{member}, so the "
            "production drive for that path cannot be performed"
        )
    recorder = Recorder()
    ledger = loaded.reservations.ReservationLedger(recorder)
    clock = _WiringClock(2000.0 + 100.0 * index)
    handler = module.OrderOutcomes(ledger, clock=clock, pending_ack_timeout_s=2.0)
    order = seam.ProposedOrder(
        client_order_id=f"wire-{index}",
        strategy_id="strat-wiring",
        symbol="ESZ6",
        side=seam.Side.LONG,
        qty=2,
        margin_per_contract=3086.25 + index,
        stop_ticks=20,
        stop_mode=seam.StopMode.FIXED,
        signal_ts=1000.0,
    )
    site = f"{OUTCOMES}:OrderOutcomes[{member}]"
    baseline = ledger.total_reserved()
    ledger.take(order, clock())
    taken = ledger.total_reserved()
    # NON-VACUITY, on every path and before any release: a release measured over
    # a reservation that was never taken proves nothing.
    if abs(taken - baseline - order.proposed_margin) > GATE_TOLERANCE:
        return [
            Finding(
                site,
                f"Σ went {baseline!r} -> {taken!r} on a take of "
                f"{order.proposed_margin!r} — no reservation was taken, so every "
                "release reading below would be about nothing",
            )
        ], ""
    tally.reservations += 1
    tally.margin += order.proposed_margin
    # The PULL verb resolves on a deadline, so the clock must cross it.
    for _ in range(4):
        clock()
    first = _fire(handler, verb, order.client_order_id, module)
    after = ledger.total_reserved()
    if after != baseline:
        return [
            Finding(
                site,
                f"the {member} terminal event moved Σ {taken!r} -> {after!r} "
                f"against a baseline of {baseline!r}: it did NOT return the "
                f"{order.proposed_margin!r} this order reserved. A LEAK — §14 "
                f"gives every reservation exactly one terminal release, "
                f"committed margin stays INFLATED by {after - baseline!r}, and "
                f"§3 Phase B denies against that inflation forever. The handler "
                f"returned {first!r}",
            )
        ], ""
    tally.releases += 1
    tally.paths.append(member)
    # AT MOST ONE: a second terminal event must be a RECORDED no-op, and Σ must
    # be BIT-identical afterwards — not merely close.
    second = _fire(handler, verb, order.client_order_id, module)
    again = ledger.total_reserved()
    if again != after:
        return [
            Finding(
                site,
                f"a SECOND {member} event for {order.client_order_id!r} moved Σ "
                f"{after!r} -> {again!r} — a DOUBLE RELEASE. Committed margin "
                f"now UNDER-counts by {after - again!r}, so §3 Phase B approves "
                f"against headroom that is already spent (§15 C1, the "
                f"double-spend race this invariant closed). The handler returned "
                f"{second!r}",
            )
        ], ""
    tally.refusals += 1
    findings: list[Finding] = []
    if len(ledger.released()) != 1:
        findings.append(
            Finding(
                site,
                f"{len(ledger.released())} RELEASED record(s) after one terminal "
                "event and one duplicate — §14 gives exactly one",
            )
        )
    if ledger.outstanding():
        findings.append(
            Finding(
                site,
                f"{len(ledger.outstanding())} reservation(s) still TAKEN after "
                f"the {member} release drained Σ to baseline — the aggregate and "
                "the store disagree about the same event",
            )
        )
    return findings, ""


def _wiring_verbs(
    loaded: Loaded, sites: dict[str, list[str]]
) -> tuple[dict[str, str], str]:
    """The module's published verb map, CROSS-CHECKED against the AST census."""
    handled = getattr(loaded.outcomes, HANDLES_ATTR, None)
    if not handled:
        return {}, (
            f"{OUTCOMES}: no {HANDLES_ATTR} map, so this gate cannot reach the "
            "module's release paths without naming one itself — which is the "
            "circularity its own test forbids"
        )
    verbs = {path.name: verb for path, verb in handled.items()}
    #: DERIVED, not declared: the paths this module is OBSERVED to book, taken
    #: from the AST census. Cross-checking the module's own map against it is
    #: what stops a subject shrinking its own drive.
    owner = Path(OUTCOMES).name
    observed = {
        member
        for member, found in sites.items()
        if member != UNREADABLE and any(site.startswith(f"{owner}:") for site in found)
    }
    if set(verbs) != observed:
        return {}, (
            f"{OUTCOMES}: the module publishes verbs for {sorted(verbs)} while "
            f"the AST census observes it booking {sorted(observed)}. A path it "
            "books but does not publish would go undriven, so the drive is "
            "unmeasured rather than smaller (§17)"
        )
    return verbs, ""


def _wiring_drive(
    loaded: Loaded, sites: dict[str, list[str]], tally: WiringTally
) -> tuple[list[Finding], str]:
    """Drive every path the handler module books, through its own public verbs."""
    if loaded.outcomes is None:
        return [], (
            f"{OUTCOMES}: the non-fill outcome handler is not importable from "
            "this tree, so the paths it books could not be driven through any "
            "production surface (§17: never a PASS)"
        )
    verbs, cannot = _wiring_verbs(loaded, sites)
    if cannot:
        return [], cannot
    findings: list[Finding] = []
    for index, member in enumerate(sorted(verbs)):
        found, blind = _drive_one_path(loaded, member, verbs[member], index, tally)
        if blind:
            return [], blind
        findings += found
    if not tally.paths and not findings:
        return [], (
            f"{OUTCOMES}: no production release path completed a drive, so a "
            "clean sheet here would be about an empty run"
        )
    return findings, ""


def _resolve_blind(
    findings: list[Finding], blind: str
) -> tuple[list[Finding], CheckResult | None]:
    """How an unmeasured half and an observed defect settle against each other.

    A blind spot never BURIES a defect that was actually observed — doctrine B.2
    cuts the other way here, because the other arms did measure their subjects.
    So: blind with nothing observed is CANNOT_MEASURE; blind WITH an observed
    defect is the FAIL, carrying the unmeasured half on the detail so the green
    half is not read as whole.
    """
    if not blind:
        return findings, None
    if not findings:
        return findings, _cannot_measure(blind)
    return findings + [Finding(f"{OUTCOMES}:wiring[enumeration]", blind)], None


def _wiring(
    home: Path, paths: tuple[str, ...], loaded: Loaded
) -> tuple[list[Finding], str, str]:
    """ARM WIRING plus the evidence sentence it derives. Lifted out of `run`."""
    tally = WiringTally()
    findings, blind = arm_wiring(home, paths, loaded, tally)
    try:
        if len(list(home.joinpath(*NIXRISK_DIR).glob("*.py"))) < MIN_CENSUS_MODULES:
            census = {ABSTAINED: ["below the census population floor"]}
        else:
            census = release_sites(home)
        evidence = _wiring_evidence(paths, census, tally)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        evidence = f"ARM WIRING census unavailable ({type(exc).__name__}: {exc})"
    return findings, blind, evidence


def arm_wiring(
    home: Path, paths: tuple[str, ...], loaded: Loaded, tally: WiringTally
) -> tuple[list[Finding], str]:
    """§14 in production: every §3 path booked somewhere, each releasing once."""
    findings, blind, sites = _wiring_structure(home, paths)
    if ABSTAINED in sites:
        return [], ""
    if blind:
        return [], blind
    driven, cannot = _wiring_drive(loaded, sites, tally)
    if cannot:
        return findings, cannot
    return findings + driven, ""


# --------------------------------------------------------------------------
# VERDICT
# --------------------------------------------------------------------------


def _wiring_evidence(
    paths: tuple[str, ...], sites: dict[str, list[str]], tally: WiringTally
) -> str:
    """The coverage sentence, DERIVED from the census taken this run.

    Never a literal. ARC 038 / F-B6 (CHECK-DEBT D3.362) measured this gate
    printing *"the Limiter's event handlers ... do not exist yet"* on every run
    while three of them existed and called this ledger — a stale UNBOUND running
    in the direction that EXCUSES coverage, which is the claim nobody re-checks.
    Regenerating the sentence from `release_sites()` at run time is what stops it
    going stale again: if a path loses its production caller the evidence says so
    on the next run, with nobody editing a string.
    """
    if ABSTAINED in sites:
        return (
            f"ARM WIRING ABSTAINED: {sites[ABSTAINED][0]} — the tree under test "
            "is not a whole Limiter package, so which §3 paths PRODUCTION books "
            "was not measured here, and is not claimed either"
        )
    wired = [member for member in paths if sites.get(member)]
    unwired = [member for member in paths if not sites.get(member)]
    booked = ", ".join(
        f"{member}={'+'.join(sorted(set(sites[member])))}" for member in wired
    )
    tail = (
        f"NO production release site: {', '.join(unwired)} — those paths LEAK "
        "(CHECK-DEBT D3.358)"
        if unwired
        else "every §3 release path has at least one production release site"
    )
    return (
        f"ARM WIRING, derived by AST census over {'/'.join(NIXRISK_DIR)}/*.py on "
        f"this run and not from any list: {len(wired)}/{len(paths)} path(s) "
        f"booked in production [{booked}]; {tail}. Of those, "
        f"{len(tally.paths)} path(s) [{', '.join(tally.paths)}] were also DRIVEN "
        f"end-to-end through the handler module's own public verbs against the "
        f"real ledger — {tally.reservations} reservation(s) over "
        f"{tally.margin!r} of margin, {tally.releases} released with Σ back to "
        f"baseline, {tally.refusals} duplicate terminal event(s) leaving Σ "
        f"bit-identical. The remainder are proven WIRED here and DRIVEN by the "
        f"gates that declare their files as SUBJECTS (check_fill_handler, "
        f"check_flatten); a second drive here would be the duplicate instrument "
        f"doctrine C.9 forbids"
    )


def _evidence(paths: tuple[str, ...], tally: Tally, wiring: str) -> str:
    return (
        f"§3 release paths {len(paths)} parsed at run time from the frozen spec "
        f"unioned with docs/SPEC-AMENDMENTS.md "
        f"[{', '.join(paths)}]; {tally.reservations} reservation(s) taken over "
        f"{tally.margin!r} of margin, {tally.releases} released, "
        f"{tally.refusals} duplicate terminal event(s) refused, "
        f"{tally.plane1_rows} Plane-1 row(s) booked; every figure read back from "
        f"the ledger's own total_reserved/outstanding/audit, none of it asserted "
        f"by this gate. {wiring}"
    )


def _preflight(
    home: Path,
) -> tuple[tuple[Loaded, dict[str, Any], tuple[str, ...]] | None, CheckResult | None]:
    """Both sides, or the one reason the comparison cannot be made."""
    paths, complaint = spec_paths(home)
    if complaint:
        return None, _cannot_measure(
            f"{complaint} (§5.3: an empty scope is never a PASS)"
        )
    loaded, error = load(home)
    if loaded is None:
        return None, _cannot_measure(error)
    members, missing = _members(loaded, paths)
    if missing:
        return None, _cannot_measure(missing)
    return (loaded, members, paths), None


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Drive §3's whole path set through the ledger. Never repairs — see above."""
    try:
        sides, refusal = _preflight(ctx.nix_home)
        if refusal is not None or sides is None:
            # `_preflight` sets exactly one member. Written rather than asserted:
            # an assert vanishes under -O, and a gate whose refusal path
            # evaporates in optimised bytecode returns a bare PASS.
            return refusal or _cannot_measure(
                f"{LEDGER}: neither a reading nor a refusal from this gate's own "
                "pre-flight, which is never a verdict"
            )
        loaded, members, paths = sides
        tally = Tally()
        findings = drive(loaded, members, tally)
        findings += arm_sigma(ctx.nix_home, loaded.reservations)
        # ARM WIRING runs LAST because it is the only arm that can turn a
        # measured FAIL into CANNOT_MEASURE: an unreadable terminal-transition
        # site means the enumeration is incomplete, and a gate that cannot
        # enumerate its own subject has not measured it (§17). The findings the
        # other arms already produced are still reported in that detail, so a
        # blind spot never buries a defect that WAS observed.
        wiring_findings, blind, wiring = _wiring(ctx.nix_home, paths, loaded)
        findings += wiring_findings
        findings, refused = _resolve_blind(findings, blind)
        if refused is not None:
            return refused
        if len(tally.paths) < MIN_TERMINAL_PATHS and not findings:
            return _cannot_measure(
                f"{LEDGER}: only {len(tally.paths)} path(s) completed a drive, "
                f"below the floor of {MIN_TERMINAL_PATHS} — a clean sheet here "
                "would be about an empty run"
            )
        evidence = _evidence(paths, tally, wiring)
        if findings:
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site="; ".join(site for site, _ in findings),
                evidence=evidence,
                detail="; ".join(f"{site}: {why}" for site, why in findings),
            )
        return CheckResult(name=NAME, status=Status.PASS, evidence=evidence)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        # Doctrine B.2: a gate that crashed measured nothing. Exit 2, never 1 —
        # exit 1 would report a violation the gate never observed.
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"gate raised {type(exc).__name__}: {exc}",
        )


# Deliberately duplicated across every checks/check_*.py: the check
# contract (§4.2) requires each module be independently runnable, so this
# block cannot be factored into a shared helper without breaking that.
# The disable pragma must be on its own line, not trailing on the `if` —
# pylint's Similarities checker (R0801) does not honour a same-line
# trailing disable comment here (verified empirically, pylint v4.0.6).
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
