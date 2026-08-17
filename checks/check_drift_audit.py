#!/usr/bin/env python3
"""§11 item 7's full-scan audit reconciles EVERY §11 item 3 aggregate, names drift, HALTs on
material.

ONE gate, ONE property, in the sense `nix_check_contract.md` §5.5 gives that rule.

The property is the FROZEN risk spec's §11 item 7 —
*"Periodic full-scan audit reconciles every running aggregate vs ground truth
(drift ⇒ audit event; material drift ⇒ HALT)"* — held over
`scripts/nixrisk/drift_audit.py`, DRIVEN, for every aggregate §11 item 3 names.

(§11 item 7 and §11 item 3 are numbered ITEMS inside section 11, not headings of their own,
so they are deliberately left unattributed here: naming the document beside them
would make `check_spec_citations` resolve a label that section 11 does not
publish as a heading, and a citation that cannot resolve is worse than one that
declines to try. Every citation in this file that CAN resolve — §12.5:631,
§12.10:751, §9:553, §17 — names its document where it is used.)

------------------------------------------------------------------------------
debug.md §7.12 — THE STANDING QUESTION, answered where the gate is built
------------------------------------------------------------------------------
*What would have to be true for this gate to PASS while measuring nothing?*

1. **THE BOOK COULD HAVE NO DRIFT.** A drift audit driven against an agreeing
   book reports `0.0` six times and never executes one line of the detection or
   escalation path. This is the arc brief's own §0a and it is the primary hazard.
   *Closed:* ARM NAMED plants a divergence in **each aggregate independently**
   and requires it to be caught and named; ARM MATERIAL plants one large enough
   to HALT and asserts the flag's own state; ARM CONTROL runs the same fixture
   unplanted and requires **silence on both planes and a clear flag**, so a
   detector that fired on everything would fail here rather than passing.

2. **ONE AGGREGATE COULD STAND IN FOR SIX.** §11 item 7 says *every* running
   aggregate. A drive that plants `balance`, catches it and generalises is the
   manufactured-coverage class. *Closed:* the plant is per aggregate, and the
   ROSTER is parsed out of §11 item 3 of the frozen document at run time, never
   spelled here and never taken from the module — deriving the expected set from
   the implementation and then proving the implementation covers it is circular.
   A roster below `MIN_AGGREGATES` is CANNOT_MEASURE, never a PASS over a set
   that silently shrank.

3. **BOTH SIDES COULD BE THE SAME ARITHMETIC.** `check_reservation_lifecycle`
   records this one level down: if the running value were computed FROM the
   store, drift would be `0.0` over any defect at all. *Closed:* ARM SEPARATION
   is static — every `_scan_*` function must read BOTH a `running.` chain and a
   `truth.` chain — plus a runtime half that perturbs **all six** aggregates at
   once and requires **all six** to report drift, which no hard-wired zero can
   survive.

4. **"MATERIAL" COULD BE A MAGIC NUMBER.** A threshold nobody can defend makes
   the HALT arm a test of that number. *Closed:* ARM FLOORS asserts the module's
   two floors ARE `reservations.AUDIT_TOLERANCE` and `reservations.MIN_MARGIN`
   by identity, and asserts statically that neither is a literal in the subject —
   so a future edit that types a number reddens instead of silently re-anchoring.

5. **THE THRESHOLD COULD BE TESTED ON ONE SIDE.** A floor driven only from above
   is not a floor. *Closed:* ARM BOUNDARY drives `classify` at the noise floor,
   just above it, just below the material floor and AT it — and requires the
   verdict to change exactly at each edge.

6. **AN ABSENT AGGREGATE COULD READ AS AGREEMENT.** Two of §11 item 3's six are not
   fields of the frozen `FinancialPicture`. An audit that scored a missing
   producer `drift=0.0` would report a healthy book over an aggregate it never
   looked at. *Closed:* ARM SEVENTEEN withholds a producer and requires
   `measurable=False`, a named reason, `complete=False` and `clean=False` — and
   requires the reading NOT to claim agreement.

7. **THE HALT COULD BE UNREACHED.** An audit that classifies drift as material,
   writes a row saying so and never calls §12.5's setter is D3.178's shape inside
   the fix for it. *Closed:* ARM MATERIAL asserts against the real `HaltFlag`'s
   own `is_set()` and against the CAUSE ON THE BOOKED PLANE-1 ROW, never a
   return value and never a mock's call count; ARM WIRING proves the machine
   cannot be constructed without a setter at all.

8. **THE ROW COULD LAND ON ONE PLANE.** §12.10:751 ticks drift-audit in BOTH
   columns. *Closed:* ARM PLANES asserts the Plane-1 row's `kind` is the seam's
   `DRIFT_AUDIT` member AND that a Plane-2 line carries the same event name.

**WHAT THIS GATE DOES NOT PROVE.** That anything in production CALLS the audit.
There is no Limiter run loop in this tree, so the subject is UNBOUND in the
D3.51 sense and the evidence says so on every run. A green here is a green about
the mechanism, never about the schedule.
"""

from __future__ import annotations

import ast
import dataclasses
import importlib
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, NamedTuple

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

# R0801 (duplicate-code): the sys.path bootstrap, the loader and the standalone
# block are identical in every check by requirement (§4.2).
# C0302 (too-many-lines): ten arms, each with its own §7.12 answer written beside
# it. `check_halt` and `check_uncalled_entry_points` carry the same disable for
# the same reason — splitting a gate across modules to satisfy a line count would
# make the property harder to read, not the gate smaller.
# R0914 (too-many-locals): an arm that plants one aggregate, drives the audit and
# reads back both planes and the flag holds all of those at once; collapsing them
# into a struct would hide what each assertion is actually reading.
# R0903 (too-few-public-methods): `Recorder`, `Lines` and `Pricer` are duck-typed
# ports with exactly the surface the subject calls. A second verb would be a port
# doing two jobs.
# pylint: disable=duplicate-code,too-many-lines,too-many-locals,too-few-public-methods
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

#: Nothing must run first. The spec is a file on disk; the audit is imported from
#: the tree under test; no check produces either.
DEPENDS_ON: tuple[str, ...] = ()
#: This gate IMPORTS `nixrisk` out of `ctx.nix_home`, so it mutates `sys.path`
#: and `sys.modules` for the duration of the load and restores both. Same
#: declaration, for the same reason, as `check_reservation_lifecycle`.
RESOURCES: tuple[str, ...] = ("interpreter:sys.modules", "interpreter:sys.path")
#: No timeout, no poll, no sleep, no subprocess. Arithmetic over dataclasses.
TIME_BOUND = False
#: NON-CORRECTABLE. The defects this gate finds are an aggregate §11 item 7 says to
#: reconcile and the audit does not, a threshold that stopped being derived, and
#: a material drift that does not reach §12.5's setter.
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the repair for an unreconciled aggregate or an unreached HALT is a change "
    "to the money-safety path, decided by a human against the frozen spec. An "
    "instrument empowered to edit the audit until its own drive came back clean "
    "would be manufacturing its own green over the one reconcile (§11 item 7) that "
    "catches the running aggregates having silently parted from the record"
)
#: Genuinely MEASURED here: the audit is imported, driven and parsed. The seam,
#: the halt machine and the ledger are READ (their types are constructed to drive
#: the audit) and each is declared by the gate that owns it.
SUBJECTS: tuple[str, ...] = ("scripts/nixrisk/drift_audit.py",)

NAME = "check_drift_audit"
ANCHOR = "scripts/nixrisk/drift_audit.py"

AUDIT = "scripts/nixrisk/drift_audit.py"
SPEC = "docs/nics_risk_subsystem_spec_v1.3.md"
PACKAGE = "nixrisk"
MODULE = "nixrisk.drift_audit"
SEAM_MODULE = "nixrisk.seam"
HALT_MODULE = "nixrisk.halt"
LEDGER_MODULE = "nixrisk.reservations"

#: Non-vacuity floor on the SPEC side (§7.12 answer 2). A FLOOR, never today's
#: count: §11 item 3 names six aggregates and a parse that started matching four
#: would still be a real reconcile, while a parse that yielded one or none would
#: agree with any audit at all.
MIN_AGGREGATES = 5

#: §11 item 3's sentence, located by its own bold lead-in and terminated by its own
#: wording. Nothing about the aggregate NAMES is spelled here — that is the
#: whole point of parsing rather than transcribing.
_ROSTER_RE = re.compile(
    r"\*\*Incremental aggregates\*\*\s*[—-]\s*(?P<body>.+?)\s+maintained as running",
    re.DOTALL,
)

#: A book big enough that no assertion in this gate is `0 == 0`: two strategies,
#: three live positions across two buckets, non-zero margin everywhere.
_BUCKETS = {"MES": "equity_index", "MNQ": "equity_index", "MCL": "energy"}
_MARGIN_PER_CONTRACT = {"MES": 1400.0, "MNQ": 2100.0, "MCL": 3300.0}
_TICK_DOLLARS = {"MES": 1.25, "MNQ": 0.50, "MCL": 10.0}
_SLIPPAGE_PAD_TICKS = 2


class Finding(NamedTuple):
    """One defect: where it is, and what is wrong. Never a bare status."""

    site: str
    why: str


class Loaded(NamedTuple):
    """The audit and the collaborators, imported out of the tree under test."""

    audit: ModuleType
    seam: ModuleType
    halt: ModuleType
    ledger: ModuleType


@dataclasses.dataclass
class Tally:
    """What the drive actually did. Non-vacuity is read off this, not asserted."""

    aggregates: list[str] = dataclasses.field(default_factory=list)
    halts: int = 0
    plane1_rows: int = 0
    plane2_lines: int = 0
    positions: int = 0
    margin: float = 0.0
    control_runs: int = 0


class Recorder:
    """A Plane-1 sink that keeps every row (§9's `enqueue`, no durability).

    Duck-typed rather than imported: the seam this gate constructs against comes
    out of `ctx.nix_home`, so a nominal `Plane1Port` from THIS process would be a
    different class object than the one the loaded audit sees.
    """

    def __init__(self) -> None:
        self.rows: list[Any] = []

    def enqueue(self, row: Any) -> None:
        """Append. Bounded by the drive, which books at most six rows per scan."""
        self.rows.append(row)

    def sync_to_disk(self) -> int:
        """Nothing is made durable here; the drive reads `rows` directly."""
        return 0

    def pending(self) -> int:
        """Every row is pending — this sink never syncs."""
        return len(self.rows)


class Lines:
    """A Plane-2 sink that keeps every structured line (§12.10:737)."""

    def __init__(self) -> None:
        self.lines: list[tuple[str, dict[str, Any]]] = []

    def emit(self, event: str, **fields: Any) -> str:
        """Record and return the rendered line. The audit never reads the return."""
        self.lines.append((event, dict(fields)))
        return f"{event} {fields}"

    def of(self, event: str) -> list[dict[str, Any]]:
        """Every line carrying this event name."""
        return [fields for name, fields in self.lines if name == event]


class Pricer:
    """§7:501's formula, satisfying the audit's `BucketPricerPort`.

    `(stop_ticks + slippage_pad) × tick_value × contracts`, transcribed from
    §7:500-504 rather than imported: `nixalloc.caps` takes an `Exposure` and a
    `CapConfig` and does not satisfy this port without an adapter the arc has not
    written (the audit's own docstring says so). What this gate proves is that the
    PORT carries the formula's three inputs, not that the allocator is wired.
    """

    def bucket_for(self, symbol: str) -> str | None:
        """§7:498's static membership. A symbol in no bucket is a real answer."""
        return _BUCKETS.get(symbol)

    def dollar_risk(self, symbol: str, contracts: int, stop_ticks: int) -> float:
        """§7:501, for `contracts` contracts of `symbol` at `stop_ticks`."""
        return (
            (float(stop_ticks) + _SLIPPAGE_PAD_TICKS)
            * _TICK_DOLLARS[symbol]
            * float(contracts)
        )


def _cannot_measure(detail: str) -> CheckResult:
    return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=detail)


# --------------------------------------------------------------------------
# LOADING — the audit comes out of the tree under test, never out of this one
# --------------------------------------------------------------------------


def _purge(saved: dict[str, ModuleType]) -> None:
    """Drop every `nixrisk*` module, restoring whatever was there before."""
    for name in [
        key for key in sys.modules if key == PACKAGE or key.startswith(f"{PACKAGE}.")
    ]:
        del sys.modules[name]
    sys.modules.update(saved)


def load(home: Path) -> tuple[Loaded | None, str]:
    """Import the audit from `home`, leaving the interpreter as it was found.

    A path-keyed import is what lets a plant live on a `tmp_path` COPY (doctrine
    C.8): the gate drives whichever tree it is pointed at, and the production
    module is never written.
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
        loaded = Loaded(
            audit=importlib.import_module(MODULE),
            seam=importlib.import_module(SEAM_MODULE),
            halt=importlib.import_module(HALT_MODULE),
            ledger=importlib.import_module(LEDGER_MODULE),
        )
        return loaded, ""
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return None, (
            f"{AUDIT}: cannot import {MODULE} from {home} — "
            f"{type(exc).__name__}: {exc}. The subject is unavailable, so "
            "nothing was measured (§17: never a PASS)"
        )
    finally:
        sys.path[:] = saved_path
        _purge(saved_modules)


def spec_aggregates(home: Path) -> tuple[tuple[str, ...], str]:
    """§11 item 3's running aggregates, PARSED FROM THE FROZEN SPEC — not from code."""
    path = home / SPEC
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return (), f"{SPEC}: unreadable ({exc}) — the expected roster has no source"
    match = _ROSTER_RE.search(text)
    if match is None:
        return (), (
            f"{SPEC}: §11 item 3's '**Incremental aggregates** — ... maintained as "
            "running' sentence did not parse. The roster this gate compares "
            "against has no source, and an empty expected set agrees with any "
            "audit at all"
        )
    body = " ".join(match.group("body").split())
    names = tuple(
        cleaned
        for cleaned in (part.replace("**", "").strip(" .") for part in body.split(","))
        if cleaned
    )
    if len(names) < MIN_AGGREGATES:
        return (), (
            f"{SPEC}: §11 item 3 yielded only {len(names)} aggregate(s) "
            f"({', '.join(names) or 'none'}), below the floor of "
            f"{MIN_AGGREGATES} — the parse stopped matching, and a shrunken "
            "expected set would compare green against a shrunken audit"
        )
    return names, ""


# --------------------------------------------------------------------------
# THE FIXTURE — a NON-TRIVIAL agreeing book, built from the loaded seam
# --------------------------------------------------------------------------


def _fixture(loaded: Loaded, tally: Tally) -> tuple[Any, Any, Any]:
    """`(Running, GroundTruth, pricer)` over a book where every side agrees.

    Three live positions, two strategies, two buckets, non-zero margin on every
    row: every assertion downstream is over real numbers, so no equality in this
    gate is `0 == 0`.
    """
    seam, aud = loaded.seam, loaded.audit
    spec = (
        # (trade_id, strategy, symbol, contracts, stop_ticks)
        ("t-1", "alpha", "MES", 3, 40),
        ("t-2", "alpha", "MNQ", 2, 55),
        ("t-3", "beta", "MCL", 1, 25),
    )
    rows = tuple(
        seam.PositionRow(
            trade_id=trade_id,
            symbol=symbol,
            strategy_id=strategy,
            size=size,
            margin=_MARGIN_PER_CONTRACT[symbol] * size,
            state=seam.PositionState.OPEN,
            stop_distance=ticks,
        )
        for trade_id, strategy, symbol, size, ticks in spec
    )
    projection = tuple(
        aud.ProjectedPosition(
            trade_id=trade_id,
            strategy_id=strategy,
            symbol=symbol,
            side="long",
            state="open",
            qty_open=size,
            qty_filled=size,
            stop_distance=ticks,
            last_event_id=index + 1,
        )
        for index, (trade_id, strategy, symbol, size, ticks) in enumerate(spec)
    )
    open_margin = sum(row.margin for row in rows)
    reservations = 4700.0
    balance = 125_000.0
    net_liq = 131_250.5
    pricer = Pricer()
    buckets: dict[str, float] = {}
    for _, _, symbol, size, ticks in spec:
        bucket = pricer.bucket_for(symbol)
        if bucket is not None:
            buckets[bucket] = buckets.get(bucket, 0.0) + pricer.dollar_risk(
                symbol, size, ticks
            )
    picture = seam.FinancialPicture(
        version=7,
        published_ts=1_000.0,
        balance=balance,
        positions=rows,
        margin_per_contract=dict(_MARGIN_PER_CONTRACT),
        sum_open_margin=open_margin,
        sum_reservations=reservations,
        committed=open_margin + reservations,
        deployable=balance - open_margin - reservations,
    )
    running = aud.Running(
        picture=picture, net_liq_mark=net_liq, bucket_exposure=dict(buckets)
    )
    truth = aud.GroundTruth(
        projection=projection,
        broker=seam.BrokerTruth(positions=rows, balance=balance, polled_at=999.0),
        net_liq=net_liq,
        reservations_scanned=reservations,
        scanned_at=1_000.0,
    )
    tally.positions = len(rows)
    tally.margin = open_margin
    return running, truth, pricer


def _perturb(loaded: Loaded, running: Any, truth: Any, member: Any, delta: float):
    """Return `(running, truth)` with ONE aggregate's RUNNING side moved by `delta`.

    The running side is what moves, never ground truth, because §11 item 7's subject is
    an incremental aggregate that has parted from the record — moving the record
    instead would measure the same arithmetic in the opposite direction and would
    NOT exercise the per-position table's asymmetric messages.
    """
    aud = loaded.audit
    agg = aud.Aggregate
    picture = running.picture
    if member is agg.OPEN_MARGIN:
        return (
            dataclasses.replace(
                running,
                picture=dataclasses.replace(
                    picture, sum_open_margin=picture.sum_open_margin + delta
                ),
            ),
            truth,
        )
    if member is agg.RESERVATIONS:
        return (
            dataclasses.replace(
                running,
                picture=dataclasses.replace(
                    picture, sum_reservations=picture.sum_reservations + delta
                ),
            ),
            truth,
        )
    if member is agg.BALANCE:
        return (
            dataclasses.replace(
                running,
                picture=dataclasses.replace(picture, balance=picture.balance + delta),
            ),
            truth,
        )
    if member is agg.NET_LIQ_MARK:
        return (
            dataclasses.replace(running, net_liq_mark=running.net_liq_mark + delta),
            truth,
        )
    if member is agg.BUCKET_EXPOSURE:
        moved = dict(running.bucket_exposure)
        first = min(moved)
        moved[first] = moved[first] + delta
        return (dataclasses.replace(running, bucket_exposure=moved), truth)
    if member is agg.POSITION_TABLE:
        # A COUNT aggregate has no magnitude to nudge: the smallest real
        # divergence is ONE row, and it is material by construction (see the
        # subject's `Unit`), so `delta` is deliberately ignored here.
        #
        # **The perturbation is the projection row's `strategy_id`, NOT a dropped
        # row, and the choice is load-bearing.** Dropping a projection row would
        # also move Σ open margin and bucket exposure, because both are scanned
        # FROM the projection — the plant would then contaminate three aggregates
        # and this gate's "planted in one, reported against one" assertion would
        # redden over its own fixture rather than over the subject. Re-attributing
        # a row changes the per-position table and nothing else.
        head = truth.projection[:-1]
        tail = truth.projection[-1]
        moved = dataclasses.replace(tail, strategy_id=f"{tail.strategy_id}-impostor")
        return (running, dataclasses.replace(truth, projection=(*head, moved)))
    raise AssertionError(f"no perturbation defined for {member!r}")


def _machine(loaded: Loaded, interval_s: float = 1.0):
    """`(audit, plane1, plane2, halt_flag)` — the real HaltFlag, never a mock.

    The cooldown floors are DERIVED from the loaded `HaltCause` enum rather than
    typed, so a cause added to §12.5's list cannot leave this gate constructing an
    invalid floor map and reporting the resulting refusal as a subject defect.
    """
    aud, halt_mod = loaded.audit, loaded.halt
    plane1, plane2 = Recorder(), Lines()
    floors = {cause.value: 60.0 for cause in halt_mod.HaltCause if cause.auto_clearable}
    flag = halt_mod.HaltFlag(plane1=plane1, plane2=plane2, floors=floors)
    audit = aud.DriftAudit(
        plane1=plane1, plane2=plane2, halt=flag, interval_s=interval_s
    )
    return audit, plane1, plane2, flag


# --------------------------------------------------------------------------
# ARMS
# --------------------------------------------------------------------------


def arm_roster(loaded: Loaded, names: tuple[str, ...]) -> list[Finding]:
    """§11 item 3's roster and the audit's `Aggregate` members agree, BOTH directions."""
    findings: list[Finding] = []
    members = {
        " ".join(member.value.split()).lower(): member
        for member in loaded.audit.Aggregate
    }
    wanted = {" ".join(name.split()).lower(): name for name in names}
    for key, name in sorted(wanted.items()):
        if key not in members:
            findings.append(
                Finding(
                    f"{AUDIT}:Aggregate",
                    f"§11 item 3 names the running aggregate {name!r} and the audit "
                    "declares no member for it — §11 item 7 says EVERY running "
                    "aggregate is reconciled, so this one is not reconciled at all",
                )
            )
    for key, member in sorted(members.items()):
        if key not in wanted:
            findings.append(
                Finding(
                    f"{AUDIT}:Aggregate.{member.name}",
                    f"the audit declares {member.value!r}, which §11 item 3 does not "
                    "name. FINDING ABOUT THE SPEC OR THE MODULE, not something to "
                    "absorb: an aggregate the frozen document does not list is "
                    "either a spec gap to raise or an invention to remove",
                )
            )
    return findings


def arm_floors(loaded: Loaded, home: Path) -> list[Finding]:
    """The two floors are IMPORTED from the ledger, and are not literals here."""
    aud, ledger = loaded.audit, loaded.ledger
    findings: list[Finding] = []
    pairs = (
        ("NOISE_FLOOR", aud.NOISE_FLOOR, "AUDIT_TOLERANCE", ledger.AUDIT_TOLERANCE),
        ("MATERIAL_FLOOR", aud.MATERIAL_FLOOR, "MIN_MARGIN", ledger.MIN_MARGIN),
    )
    for own, value, source, expected in pairs:
        if value != expected:
            findings.append(
                Finding(
                    f"{AUDIT}:{own}",
                    f"{own} is {value!r} but reservations.{source} is "
                    f"{expected!r}. The band that decides whether §11 item 7 escalates "
                    "to HALT has stopped being derived from the figure that was "
                    "set by measurement — it is now a number of its own, and a "
                    "threshold nobody can defend is a magic number",
                )
            )
    if aud.MATERIAL_FLOOR <= aud.NOISE_FLOOR:
        findings.append(
            Finding(
                f"{AUDIT}:MATERIAL_FLOOR",
                f"the material floor {aud.MATERIAL_FLOOR!r} is not above the noise "
                f"floor {aud.NOISE_FLOOR!r}: the DRIFT band between them is empty, "
                "so every disagreement that clears the noise floor HALTs and "
                "§11 item 7's two-tier response has collapsed to one tier",
            )
        )
    source_text = (home / AUDIT).read_text(encoding="utf-8")
    tree = ast.parse(source_text)
    for node in tree.body:
        if not isinstance(node, ast.AnnAssign) or node.value is None:
            continue
        target = node.target
        if not isinstance(target, ast.Name) or target.id not in {
            "NOISE_FLOOR",
            "MATERIAL_FLOOR",
        }:
            continue
        if isinstance(node.value, ast.Constant):
            findings.append(
                Finding(
                    f"{AUDIT}:{target.id}",
                    f"{target.id} is assigned the literal {node.value.value!r} "
                    "instead of the imported ledger constant. A typed threshold "
                    "is an anchor that moves independently of the measurement "
                    "that justified it (debug.md §7.4)",
                )
            )
    return findings


def arm_boundary(loaded: Loaded) -> list[Finding]:
    """The band's edges, driven from BOTH sides. A floor tested once is untested."""
    aud = loaded.audit
    noise, material = aud.NOISE_FLOOR, aud.MATERIAL_FLOOR
    unit = aud.Unit.CURRENCY
    cases = (
        (0.0, False, False, "an exactly-agreeing pair"),
        (noise, False, False, "AT the noise floor — representation, not drift"),
        (noise * 10.0, True, False, "just above the noise floor"),
        (material * 0.5, True, False, "half the material floor"),
        (material, True, True, "AT the material floor — the escalating edge"),
        (-material, True, True, "AT the material floor, NEGATIVE (Σ under-counts)"),
        (material * 10.0, True, True, "well above the material floor"),
    )
    findings: list[Finding] = []
    for drift, want_drifted, want_material, label in cases:
        got_drifted, got_material = aud.classify(drift, unit)
        if (got_drifted, got_material) != (want_drifted, want_material):
            findings.append(
                Finding(
                    f"{AUDIT}:classify",
                    f"{label}: classify({drift!r}) returned "
                    f"(drifted={got_drifted!r}, material={got_material!r}), "
                    f"expected (drifted={want_drifted!r}, material={want_material!r}). "
                    f"Floors in force: noise {noise!r}, material {material!r}",
                )
            )
    # COUNT has no noise floor at all, and that is a separate claim.
    for drift, want in ((0.0, False), (1.0, True), (-1.0, True)):
        got_drifted, got_material = aud.classify(drift, aud.Unit.COUNT)
        if (got_drifted, got_material) != (want, want):
            findings.append(
                Finding(
                    f"{AUDIT}:classify",
                    f"a COUNT drift of {drift!r} classified "
                    f"(drifted={got_drifted!r}, material={got_material!r}), expected "
                    f"({want!r}, {want!r}). Contract counts are integers and "
                    "integer arithmetic is exact, so a tolerance here would be a "
                    "tolerance for losing whole positions",
                )
            )
    return findings


def arm_control(loaded: Loaded, tally: Tally) -> list[Finding]:
    """An agreeing book is SILENT on both planes and leaves the flag clear."""
    running, truth, pricer = _fixture(loaded, tally)
    audit, plane1, plane2, flag = _machine(loaded)
    outcome = audit.run(running, truth, pricer=pricer)
    tally.control_runs += 1
    findings: list[Finding] = []
    if not outcome.complete:
        findings.append(
            Finding(
                f"{AUDIT}:DriftAudit.run",
                "the CONTROL scan reports incomplete over a fixture that supplies "
                "every producer: "
                + "; ".join(r.unmeasurable_reason for r in outcome.unmeasurable),
            )
        )
    if not outcome.clean or outcome.drifted:
        findings.append(
            Finding(
                f"{AUDIT}:DriftAudit.run",
                "the CONTROL scan found drift over a book where every aggregate "
                "agrees exactly: " + "; ".join(r.detail for r in outcome.drifted),
            )
        )
    if plane1.rows or plane2.lines:
        findings.append(
            Finding(
                f"{AUDIT}:DriftAudit.run",
                f"the CONTROL scan wrote {len(plane1.rows)} Plane-1 row(s) and "
                f"{len(plane2.lines)} Plane-2 line(s). §11 item 7 makes the audit event "
                "conditional on DRIFT; a detector that fires on an agreeing book "
                "fires on everything, and would pass every plant arm in this gate "
                "while discriminating nothing",
            )
        )
    halted, why = flag.is_set()
    if halted:
        findings.append(
            Finding(
                f"{AUDIT}:DriftAudit.run",
                f"the CONTROL scan HALTed an agreeing book: {why!r}",
            )
        )
    return findings


def arm_named(loaded: Loaded, tally: Tally) -> list[Finding]:
    """Each aggregate, planted ALONE, is caught and NAMED. One drive per member."""
    aud = loaded.audit
    findings: list[Finding] = []
    # Sub-material for every currency aggregate: comfortably above the noise
    # floor and comfortably below the material floor, both by a factor derived
    # from the floors themselves rather than typed.
    delta = aud.MATERIAL_FLOOR / 4.0
    for member in aud.Aggregate:
        running, truth, pricer = _fixture(loaded, tally)
        moved_running, moved_truth = _perturb(loaded, running, truth, member, delta)
        audit, plane1, plane2, flag = _machine(loaded)
        outcome = audit.run(moved_running, moved_truth, pricer=pricer)
        tally.aggregates.append(member.name)
        tally.plane1_rows += len(plane1.rows)
        tally.plane2_lines += len(plane2.lines)
        drifted = {reading.aggregate for reading in outcome.drifted}
        if member not in drifted:
            findings.append(
                Finding(
                    f"{AUDIT}:Aggregate.{member.name}",
                    f"a divergence planted in {member.value!r} alone was NOT "
                    f"detected. Reported drift: "
                    f"{ {r.aggregate.name: r.drift for r in outcome.readings}!r}. "
                    "§11 item 7 reconciles every running aggregate; this one is "
                    "reconciled in name only",
                )
            )
            continue
        if drifted != {member}:
            findings.append(
                Finding(
                    f"{AUDIT}:Aggregate.{member.name}",
                    f"a divergence planted in {member.value!r} alone was reported "
                    f"against {sorted(m.name for m in drifted)!r}. An audit that "
                    "cannot attribute drift to ONE aggregate cannot tell an "
                    "operator which running value to distrust",
                )
            )
        reading = next(r for r in outcome.readings if r.aggregate is member)
        if member.value not in reading.detail:
            findings.append(
                Finding(
                    f"{AUDIT}:Aggregate.{member.name}",
                    f"the finding for {member.value!r} does not NAME the aggregate "
                    f"in its own detail: {reading.detail!r}",
                )
            )
        rows = [
            row for row in plane1.rows if row.kind is loaded.seam.EventKind.DRIFT_AUDIT
        ]
        if len(rows) != 1:
            findings.append(
                Finding(
                    f"{AUDIT}:Aggregate.{member.name}",
                    f"one planted divergence produced {len(rows)} Plane-1 "
                    "drift_audit row(s), expected exactly one — §11 item 7's audit "
                    "event is per drifted aggregate",
                )
            )
        elif dict(rows[0].fields).get("aggregate") != member.name.lower():
            findings.append(
                Finding(
                    f"{AUDIT}:Aggregate.{member.name}",
                    f"the Plane-1 row names aggregate "
                    f"{dict(rows[0].fields).get('aggregate')!r}, not "
                    f"{member.name.lower()!r} — the row cannot be attributed",
                )
            )
        halted, _ = flag.is_set()
        # POSITION_TABLE is a COUNT and is material at one row by construction.
        expect_halt = member is aud.Aggregate.POSITION_TABLE
        if halted is not expect_halt:
            findings.append(
                Finding(
                    f"{AUDIT}:Aggregate.{member.name}",
                    f"a SUB-MATERIAL divergence of {delta!r} in {member.value!r} "
                    f"left halted={halted!r}, expected {expect_halt!r}. §11 item 7 "
                    "escalates only MATERIAL drift; a detector that HALTs on every "
                    "disagreement makes the material floor decorative",
                )
            )
        if halted:
            tally.halts += 1
    return findings


def arm_material(loaded: Loaded, tally: Tally) -> list[Finding]:
    """A MATERIAL divergence reaches §12.5's setter, in the flag's own state."""
    aud = loaded.audit
    findings: list[Finding] = []
    delta = aud.MATERIAL_FLOOR * 1_000.0
    for member in aud.Aggregate:
        running, truth, pricer = _fixture(loaded, tally)
        moved_running, moved_truth = _perturb(loaded, running, truth, member, delta)
        audit, plane1, _plane2, flag = _machine(loaded)
        outcome = audit.run(moved_running, moved_truth, pricer=pricer)
        halted, why = flag.is_set()
        if not halted:
            findings.append(
                Finding(
                    f"{AUDIT}:Aggregate.{member.name}",
                    f"MATERIAL drift of {delta!r} in {member.value!r} did NOT set "
                    "the HALT flag. §11 item 7: *material drift ⇒ HALT*; §12.5 names "
                    "`aggregate-drift` as a setter. The audit reported "
                    f"halted={outcome.halted!r} and wrote {len(plane1.rows)} "
                    "row(s) — a report is not a gate on money",
                )
            )
            continue
        tally.halts += 1
        # THE CAUSE IS READ OFF THE AUDITED ROW, NOT OFF THE FLAG'S MEMORY, and
        # the choice is deliberate twice over. §12.5:633 makes every set an
        # AUDITED event with reason, so the row is the artifact the rule is about
        # — an in-memory cause that never reached Plane 1 would satisfy a
        # `flag.active()` assertion and fail the spec. And reading `active()` here
        # would make this gate the only caller of that verb in the tree, which
        # silently moves `halt.py::HaltFlag.active` out of another gate's uncalled
        # baseline: an instrument must not change the population a different
        # instrument is measuring.
        booked = [
            row for row in plane1.rows if row.kind is loaded.seam.EventKind.HALT_SET
        ]
        causes = [dict(row.fields).get("cause") for row in booked]
        drift_cause = loaded.halt.HaltCause.AGGREGATE_DRIFT.value
        if drift_cause not in causes:
            findings.append(
                Finding(
                    f"{AUDIT}:Aggregate.{member.name}",
                    f"the booked HALT row(s) name cause {causes!r}, not "
                    f"{drift_cause!r}. §12.5:631's cause list is closed and every "
                    "set/clear is an audited event WITH reason — a HALT booked "
                    "under the wrong cause cannot auto-clear on the right condition",
                )
            )
        if member.value not in why:
            findings.append(
                Finding(
                    f"{AUDIT}:Aggregate.{member.name}",
                    f"the HALT reason does not NAME the aggregate that caused it: "
                    f"{why!r}",
                )
            )
        halt_rows = booked or [
            row for row in plane1.rows if row.kind is loaded.seam.EventKind.HALT_SET
        ]
        drift_rows = [
            row for row in plane1.rows if row.kind is loaded.seam.EventKind.DRIFT_AUDIT
        ]
        if not halt_rows or not drift_rows:
            findings.append(
                Finding(
                    f"{AUDIT}:Aggregate.{member.name}",
                    f"material drift produced {len(halt_rows)} halt_set row(s) and "
                    f"{len(drift_rows)} drift_audit row(s); §12.10 requires both "
                    "events on Plane 1",
                )
            )
        elif plane1.rows.index(halt_rows[0]) > plane1.rows.index(drift_rows[0]):
            findings.append(
                Finding(
                    f"{AUDIT}:DriftAudit.run",
                    "the drift_audit row was written BEFORE the HALT was set. "
                    "Money keeps flowing for the duration of the log write, which "
                    "inverts the priority `nixrisk.halt` fixes one level down: the "
                    "flag flips before any I/O the log path might block on",
                )
            )
    return findings


def arm_planes(loaded: Loaded, tally: Tally) -> list[Finding]:
    """§12.10:751 ticks drift-audit in BOTH columns. Both, or the row is half-written."""
    aud = loaded.audit
    running, truth, pricer = _fixture(loaded, tally)
    moved_running, moved_truth = _perturb(
        loaded, running, truth, aud.Aggregate.BALANCE, aud.MATERIAL_FLOOR / 4.0
    )
    audit, plane1, plane2, _flag = _machine(loaded)
    audit.run(moved_running, moved_truth, pricer=pricer)
    findings: list[Finding] = []
    kind = getattr(loaded.seam.EventKind, "DRIFT_AUDIT", None)
    if kind is None:
        return [
            Finding(
                "scripts/nixrisk/seam.py:EventKind",
                "the seam declares no DRIFT_AUDIT member, so a §11 item 7 audit event "
                "cannot be written under its own kind. §12.10:751 lists the event "
                "and `plane1_event_enum` already carries `drift_audit`",
            )
        ]
    if not any(row.kind is kind for row in plane1.rows):
        findings.append(
            Finding(
                f"{AUDIT}:DriftAudit.run",
                f"drift produced no Plane-1 row of kind {kind!r}; rows written: "
                f"{[getattr(r.kind, 'value', r.kind) for r in plane1.rows]!r}",
            )
        )
    if not plane2.of(aud.PLANE2_EVENT):
        findings.append(
            Finding(
                f"{AUDIT}:DriftAudit.run",
                f"drift produced no Plane-2 line named {aud.PLANE2_EVENT!r}; lines "
                f"emitted: {[name for name, _ in plane2.lines]!r}. §12.10:751 ticks "
                "this event in BOTH planes, and Plane 2 is what survives a Postgres "
                "outage (§12.4) — exactly when Plane 1 degrades",
            )
        )
    for row in plane1.rows:
        if row.kind is not kind:
            continue
        for field in ("strategy_id", "reason"):
            if not str(getattr(row, field, "") or "").strip():
                findings.append(
                    Finding(
                        f"{AUDIT}:DriftAudit.run",
                        f"the drift_audit row carries an empty {field!r}. §9:553 "
                        "requires timestamp + strategy_id + trade_id + reason on "
                        "every row and `plane1.sql` CHECKs the non-blank",
                    )
                )
    return findings


def _seventeen_case(
    loaded: Loaded, tally: Tally, field: str, member: Any, side: str
) -> list[Finding]:
    """ONE producer withheld, and everything §17 requires of the result.

    Split out of `arm_seventeen` for a measured reason and not a stylistic one:
    the arm scored 16 on `complexipy` against a ceiling of 15. The split is at
    the loop body, so each case is still one whole §17 assertion set and nothing
    was dropped to buy the number down.
    """
    aud = loaded.audit
    findings: list[Finding] = []
    running, truth, pricer = _fixture(loaded, tally)
    if side == "running":
        running = dataclasses.replace(running, **{field: None})
    else:
        truth = dataclasses.replace(truth, **{field: None})
    audit, plane1, plane2, flag = _machine(loaded)
    outcome = audit.run(running, truth, pricer=pricer)
    reading = next(r for r in outcome.readings if r.aggregate is member)
    if reading.measurable:
        findings.append(
            Finding(
                f"{AUDIT}:Aggregate.{member.name}",
                f"with {field!r} withheld the audit still reports "
                f"{member.value!r} measurable (drift {reading.drift!r}). A "
                "safety property proven while its subject is unavailable is "
                "not proven (nix_check_contract.md §17) — and 'I could not "
                "look' scored as 'they agree' is the worst available default",
            )
        )
    if not reading.unmeasurable_reason.strip():
        findings.append(
            Finding(
                f"{AUDIT}:Aggregate.{member.name}",
                "the unmeasurable reading carries no reason, so nobody can "
                "tell WHY the aggregate was not reconciled (check contract "
                "v2 §11: assert the reason, never the status alone)",
            )
        )
    if outcome.complete or outcome.clean:
        findings.append(
            Finding(
                f"{AUDIT}:AuditOutcome",
                f"with {member.value!r} unscannable the outcome reports "
                f"complete={outcome.complete!r} clean={outcome.clean!r}. Five "
                "of six agreeing and the sixth never looked at is not a "
                "healthy book",
            )
        )
    if flag.is_set()[0]:
        findings.append(
            Finding(
                f"{AUDIT}:DriftAudit.run",
                f"a missing producer for {member.value!r} HALTed trading. An "
                "absent instrument is not evidence of drift, and §12.4's whole "
                "rule is that a degraded record is not degraded trading",
            )
        )
    if not plane2.of(aud.PLANE2_INCOMPLETE_EVENT):
        findings.append(
            Finding(
                f"{AUDIT}:DriftAudit.run",
                f"the unscannable aggregate {member.value!r} produced no "
                "Plane-2 line, so `complete=False` reaches nobody outside the "
                "return value",
            )
        )
    if plane1.rows:
        findings.append(
            Finding(
                f"{AUDIT}:DriftAudit.run",
                f"an unscannable aggregate wrote {len(plane1.rows)} Plane-1 "
                "row(s). A diagnostic about the instrument is not a money "
                "transition and does not belong in the append-only record",
            )
        )
    return findings


def arm_seventeen(loaded: Loaded, tally: Tally) -> list[Finding]:
    """An aggregate with no producer is NAMED unmeasurable, never scored agreeing.

    Three withholdings, one per producer that can genuinely be absent: the two
    §11 item 3 aggregates the frozen `FinancialPicture` does not carry, and the
    reservation ledger's own full scan.
    """
    aud = loaded.audit
    withheld = (
        ("net_liq_mark", aud.Aggregate.NET_LIQ_MARK, "running"),
        ("bucket_exposure", aud.Aggregate.BUCKET_EXPOSURE, "running"),
        ("reservations_scanned", aud.Aggregate.RESERVATIONS, "truth"),
    )
    findings: list[Finding] = []
    for field, member, side in withheld:
        findings += _seventeen_case(loaded, tally, field, member, side)
    return findings


def arm_separation(loaded: Loaded, home: Path, tally: Tally) -> list[Finding]:
    """Neither side of the reconcile is derived from the other. Static + driven."""
    findings: list[Finding] = []
    source = (home / AUDIT).read_text(encoding="utf-8")
    tree = ast.parse(source)
    scans = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("_scan_")
    ]
    if len(scans) < MIN_AGGREGATES:
        findings.append(
            Finding(
                f"{AUDIT}:_scan_*",
                f"only {len(scans)} per-aggregate scan function(s) found, below "
                f"the floor of {MIN_AGGREGATES}. Either the reconcile collapsed "
                "into one function that cannot be inspected per aggregate, or the "
                "naming convention this arm reads moved and the arm is now blind",
            )
        )
    for node in scans:
        roots = {
            sub.id
            for sub in ast.walk(node)
            if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load)
        }
        if "running" not in roots or "truth" not in roots:
            findings.append(
                Finding(
                    f"{AUDIT}:{node.name}",
                    f"{node.name} reads {sorted(roots & {'running', 'truth'})!r} — "
                    "a reconcile that touches only one side is comparing a value "
                    "with itself or with a constant, and reports drift 0.0 over "
                    "any defect at all (check_reservation_lifecycle ARM SIGMA, one "
                    "level down)",
                )
            )
    # The DRIVEN half: move every aggregate at once and require every one to say so.
    aud = loaded.audit
    running, truth, pricer = _fixture(loaded, tally)
    delta = aud.MATERIAL_FLOOR / 4.0
    for member in aud.Aggregate:
        running, truth = _perturb(loaded, running, truth, member, delta)
    audit, _plane1, _plane2, _flag = _machine(loaded)
    outcome = audit.run(running, truth, pricer=pricer)
    silent = [
        reading.aggregate.name
        for reading in outcome.readings
        if not reading.drifted and reading.measurable
    ]
    if silent:
        findings.append(
            Finding(
                f"{AUDIT}:full_scan",
                f"with EVERY aggregate perturbed, {sorted(silent)!r} still report "
                "no drift. An aggregate that cannot report drift under any input "
                "is wired to a constant or to its own ground truth",
            )
        )
    return findings


def arm_wiring(loaded: Loaded) -> list[Finding]:
    """The machine cannot be built without a HALT setter, or with a hot-path period."""
    aud = loaded.audit
    findings: list[Finding] = []
    plane1, plane2 = Recorder(), Lines()
    try:
        aud.DriftAudit(plane1=plane1, plane2=plane2, interval_s=1.0)  # type: ignore[call-arg]
    except TypeError:
        pass
    else:
        findings.append(
            Finding(
                f"{AUDIT}:DriftAudit.__init__",
                "a DriftAudit constructed with NO halt setter was accepted. It "
                "would find material drift, write a row saying so, and leave money "
                "flowing — D3.178's shape (a verb nobody calls) inside the fix for "
                "it. §11 item 7's escalation is not optional wiring",
            )
        )
    _audit, _p1, _p2, flag = _machine(loaded)
    for bad in (0.0, -1.0, aud.MIN_INTERVAL_S / 2.0):
        try:
            aud.DriftAudit(plane1=plane1, plane2=plane2, halt=flag, interval_s=bad)
        except aud.KnobError:
            continue
        findings.append(
            Finding(
                f"{AUDIT}:DriftAudit.__init__",
                f"an audit period of {bad!r} was accepted. §11 makes the entry "
                "pathway cache-reads-and-arithmetic only and §11 item 7 schedules the "
                "full scan OFF the hot path; an unbounded-frequency full scan puts "
                "it back on",
            )
        )
    return findings


# --------------------------------------------------------------------------
# VERDICT
# --------------------------------------------------------------------------


def _evidence(names: tuple[str, ...], tally: Tally) -> str:
    return (
        f"§11 item 3 running aggregates {len(names)} parsed at run time from the frozen "
        f"spec [{', '.join(names)}]; {len(tally.aggregates)} independent plant "
        f"drive(s) over a book of {tally.positions} live position(s) carrying "
        f"{tally.margin!r} of open margin; {tally.plane1_rows} Plane-1 row(s) and "
        f"{tally.plane2_lines} Plane-2 line(s) written under drift, "
        f"{tally.halts} HALT(s) set under §12.5 aggregate_drift against the real "
        f"HaltFlag's own is_set() and the CAUSE on the booked HALT_SET "
        f"row, and {tally.control_runs} zero-drift "
        f"CONTROL run(s) that wrote NOTHING to either plane. UNBOUND (D3.51): "
        f"drives the AUDIT, never a Limiter run loop — nothing in this tree "
        f"schedules it, so a green is about the mechanism and never the schedule"
    )


def _preflight(
    home: Path,
) -> tuple[tuple[Loaded, tuple[str, ...]] | None, CheckResult | None]:
    """Both sides, or the one reason the comparison cannot be made."""
    names, complaint = spec_aggregates(home)
    if complaint:
        return None, _cannot_measure(complaint)
    loaded, why = load(home)
    if loaded is None:
        return None, _cannot_measure(why)
    return (loaded, names), None


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Drive §11 item 7 over every §11 item 3 aggregate. Never repairs — see above."""
    try:
        sides, refusal = _preflight(ctx.nix_home)
        if refusal is not None or sides is None:
            # Written rather than asserted: an assert vanishes under -O, and a
            # gate whose refusal path evaporates in optimised bytecode returns a
            # bare PASS.
            return refusal or _cannot_measure(
                f"{AUDIT}: neither a reading nor a refusal from this gate's own "
                "pre-flight, which is never a verdict"
            )
        loaded, names = sides
        tally = Tally()
        findings: list[Finding] = []
        findings += arm_roster(loaded, names)
        findings += arm_floors(loaded, ctx.nix_home)
        findings += arm_boundary(loaded)
        findings += arm_control(loaded, tally)
        findings += arm_named(loaded, tally)
        findings += arm_material(loaded, tally)
        findings += arm_planes(loaded, tally)
        findings += arm_seventeen(loaded, tally)
        findings += arm_separation(loaded, ctx.nix_home, tally)
        findings += arm_wiring(loaded)
        if tally.control_runs == 0 or tally.positions == 0 or tally.margin == 0.0:
            return _cannot_measure(
                f"{AUDIT}: the drive reached {tally.positions} position(s) over "
                f"{tally.margin!r} of margin with {tally.control_runs} control "
                "run(s) — a clean sheet here would be about an empty book"
            )
        evidence = _evidence(names, tally)
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
