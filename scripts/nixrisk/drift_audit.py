# pylint: disable=too-many-lines
# 1011 lines, and the excess is PROSE — §11 item 7 answered aggregate by
# aggregate, with the materiality argument beside the constant it derives.
# Doctrine B.7 puts the argument next to the instrument it argues for.
# pylint: disable=duplicate-code
# R0801 must be disabled at the TOP of the file, before the docstring: the
# similarities checker reports at module scope and a pragma further down
# does not reach it. Same placement as check_nixverify_init.py and a dozen
# siblings. What it pairs here is this arc's Plane-1 modules by their shared
# psql helpers, declaration blocks and scratch-cluster fixtures — required by
# §4.2 (every check independently runnable and self-contained), and written
# by four sub-agents in worktrees that could not see each other.
"""§11 item 7's periodic full-scan audit: every running aggregate vs ground truth.

§11 item 7 verbatim (`nics_risk_subsystem_spec_v1.3.md:592-593`):

    *"Periodic **full-scan audit** reconciles every running aggregate vs ground
    truth (drift ⇒ audit event; material drift ⇒ HALT)."*

and §11 item 3:586-587 names the running aggregates the audit is accountable to:

    *"**Incremental aggregates** — Σ open margin, **Σ reservations**, bucket
    exposure, **net-liq mark**, **balance**, per-position table maintained as
    running values on fill/close/tick ⇒ all gate checks O(1)."*

`§12.5:631` names `aggregate-drift` as one of six HALT setters; `§12.10:751`
routes the drift-audit event to **both** planes.

------------------------------------------------------------------------------
THE ONE THING THIS MODULE EXISTS TO AVOID: COMPARING A VALUE WITH ITSELF
------------------------------------------------------------------------------
`check_reservation_lifecycle`'s ARM SIGMA already records the shape one level
down: *"if `total_reserved()` were computed FROM the store, the two sides of that
reconcile would be the same arithmetic over the same data and drift would be 0.0
over any defect at all."*

The same trap governs every line here. So the two sides come from structurally
different producers and are never derived from one another:

  * the RUNNING side is read off the published `FinancialPicture` (§11 item 3's
    incremental aggregates, maintained on fill/close/tick) and off the two
    running values the frozen snapshot does not carry (see `Running`);
  * the GROUND-TRUTH side is recomputed with `math.fsum` from the Plane-1 log
    projection (`databases/schema/plane1.sql`'s `plane1_positions`) and from a
    broker poll (`seam.BrokerTruth`).

Nothing in this module reads a picture field to build a scanned figure, with one
declared and deliberate exception: `picture.margin_per_contract` is used to price
the projection's contract counts for Σ open margin. That map is a **price list**,
not an aggregate — the projection has no margin column (see `ProjectedPosition`)
— and the QUANTITIES it is applied to come entirely from ground truth. A defect
in the running Σ is therefore still visible; a defect in the margin cache itself
is NOT this audit's subject and is named as a non-claim in
`downloads/ARC035_D_SELFAUDIT.md`.

------------------------------------------------------------------------------
"MATERIAL" — DERIVED FROM TWO MEASURED CONSTANTS, NEVER TYPED HERE
------------------------------------------------------------------------------
§11 item 7 escalates only *material* drift to HALT and defines neither word. A number
chosen by taste would make every HALT arm a test of that number; a number tuned
against an observed run is an anchor that moves (`debug.md` §7.4). Both figures
below are therefore **imported** from `nixrisk.reservations`, where each was
already set by measurement, and the band is a consequence of them:

  | band     | condition                                  | §11 item 7 consequence        |
  |----------|--------------------------------------------|--------------------------|
  | noise    | `abs(drift) <= NOISE_FLOOR`   (1e-9)       | nothing                  |
  | drift    | `NOISE_FLOOR < abs(drift) < MATERIAL_FLOOR`| audit event, both planes |
  | material | `abs(drift) >= MATERIAL_FLOOR` (1e-3)      | audit event + HALT       |

**The defence, in one sentence:** *material* means the disagreement is at least
the size of one whole commitment the system can hold, and the smallest such
commitment is `reservations.MIN_MARGIN` — so a drift at or above it can be a
lost or double-counted commitment, and a drift below it provably cannot be one.

**The arithmetic backs the band widths rather than decorating them.** IEEE-754
doubles carry ~1e-16 relative error, so a running sum over an account of size `N`
accumulates on the order of `N × 1e-16` per operation: at `N = 1e6` over 1e4
operations that is ~1e-6 — inside the DRIFT band, above the noise floor, and four
orders BELOW the material floor. The bands are therefore separated from realistic
float accumulation on both sides rather than straddling it.

**Integer-valued aggregates get no noise floor at all**, and that is a separate
claim with its own defence: a tolerance exists because a float sum of decimals is
inexact. Contract counts are integers and integer arithmetic is exact, so any
non-zero difference in the per-position table — a row on one side only, a size
mismatch, a state mismatch — is a REAL difference. A tolerance on an integer
count would be a tolerance for losing positions.

------------------------------------------------------------------------------
§17 — AN AGGREGATE WHOSE PRODUCER IS ABSENT IS NOT AN AGGREGATE THAT AGREES
------------------------------------------------------------------------------
Two of §11 item 3's six running aggregates — bucket exposure and the net-liq mark —
are **not fields of the frozen `FinancialPicture`**. They are held elsewhere
(`nixalloc.caps` prices the first; `nixrisk.survival` holds the second). When a
caller supplies neither the running value nor the means to scan it, this audit
reports that aggregate `measurable=False` **by name** and the outcome is
`complete=False`. It never scores the aggregate `drift=0.0`, because "I could not
look" and "I looked and they agree" are different facts and a safety property
proven while its subject is unavailable is not proven (`nix_check_contract.md`
§17).

------------------------------------------------------------------------------
SOLE WRITER (§9, §12.10: *"no new writers, ever"*)
------------------------------------------------------------------------------
This module opens no database connection and holds no credential. It writes
Plane 1 through the frozen `seam.Plane1Port` — the Limiter's own
enqueue → WAL → group-commit path — and Plane 2 through the same `emit` shape
`nixrisk.halt` and `nixrisk.supervision` already declare. It is a caller of the
sole writer, not a second author.

------------------------------------------------------------------------------
WHAT THIS MODULE DOES NOT CLAIM
------------------------------------------------------------------------------
  * **No durability claim.** Ground truth is read as it currently stands.
    Nothing here proves any projection row survived a crash; that is measured at
    a real durability boundary (`pg_ctl -m immediate`) and it is not this file.
  * **No liveness claim.** A clean audit writes to NEITHER plane, because §11 item 7
    says *drift ⇒ audit event* and a clean scan is not an event; a Plane-1
    heartbeat row would be a non-transition in the money log. The cost is
    honest and recorded: a clean audit is indistinguishable from an audit that
    stopped running, and closing that needs a §12.9 liveness alert this arc does
    not build.
  * **No production-schedule claim.** `due` / `run_if_due` implement §11 item 7's
    *periodic*, but there is no Limiter run loop in this tree to call them from.
"""

from __future__ import annotations

# pylint: disable=duplicate-code
# R0801 across this arc's Plane-1 modules pairs their DECLARATION BLOCKS,
# their `psql` subprocess helpers and their scratch-cluster fixtures. That
# shape is REQUIRED, not accidental: §4.2 makes every check independently
# runnable and self-contained, and four sub-agents wrote against the same
# frozen schema in worktrees that could not see each other. The same
# reasoning a dozen existing checks already state at this exact site.
import dataclasses
import enum
import math
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any, Final, Protocol, runtime_checkable

from nixrisk.halt import HaltCause
from nixrisk.reservations import AUDIT_TOLERANCE, MIN_MARGIN
from nixrisk.seam import BrokerTruth, EventKind, EventRow, FinancialPicture, PositionRow

__all__ = [
    "MATERIAL_FLOOR",
    "NOISE_FLOOR",
    "PLANE2_EVENT",
    "PLANE2_INCOMPLETE_EVENT",
    "Aggregate",
    "AggregateDrift",
    "AuditOutcome",
    "BucketPricerPort",
    "DriftAudit",
    "GroundTruth",
    "ProjectedPosition",
    "Running",
    "Unit",
    "classify",
    "full_scan",
]

#: §12.5:631's setter this audit actuates. Spelled once, imported not restated.
CAUSE: Final[HaltCause] = HaltCause.AGGREGATE_DRIFT

#: Below this a disagreement is float representation, not a lost commitment.
#: IMPORTED from the ledger that set it by measurement — see the module
#: docstring. Restating `1e-9` here would be directive 3's drift.
NOISE_FLOOR: Final[float] = AUDIT_TOLERANCE

#: At or above this a disagreement is at least one whole admissible commitment,
#: which is what makes it MATERIAL. Also imported, for the same reason.
MATERIAL_FLOOR: Final[float] = MIN_MARGIN

#: The §12.10:751 event name, on both planes. Matches `EventKind.DRIFT_AUDIT`
#: and `plane1_event_enum`'s `drift_audit` member, so a reader grepping one
#: finds the others.
PLANE2_EVENT: Final[str] = "drift_audit"

#: Plane 2 ONLY. An aggregate that could not be scanned is a diagnostic fact
#: about the instrument, not a money transition, so it gets no Plane-1 row —
#: but it must not be silent either, or `complete=False` reaches nobody.
PLANE2_INCOMPLETE_EVENT: Final[str] = "drift_audit_incomplete"

#: The projection states that are part of the OPEN book. `plane1_positions`
#: declares `plane1_position_state_enum AS ENUM ('open', 'partial', 'closed')`;
#: a closed position is history and is not an aggregate input.
LIVE_PROJECTION_STATES: Final[tuple[str, ...]] = ("open", "partial")

#: §11 item 7 says *periodic*. A floor rather than a default: an audit that may run
#: arbitrarily often is a full scan on the hot path, which is the one thing §11
#: exists to forbid. One second is three orders above any plausible gate
#: evaluation and is a floor, never a recommendation.
MIN_INTERVAL_S: Final[float] = 1.0


class DriftAuditError(RuntimeError):
    """Base for every refusal this audit raises. Never caught internally."""


class KnobError(ValueError):
    """A tunable outside its admissible range. Raised at construction (§12A)."""


class Unit(enum.Enum):
    """What kind of number an aggregate's drift is, which decides its floor.

    The distinction is load-bearing, not cosmetic: `CURRENCY` drift is compared
    against a noise floor because float sums of decimals are inexact; `COUNT`
    drift is not, because integer arithmetic is exact and a tolerance on a
    position count would be a tolerance for losing positions.
    """

    CURRENCY = "currency"
    COUNT = "count"


class Aggregate(enum.Enum):
    """§11 item 3:586-587's six running aggregates, TRANSCRIBED and closed.

    The value of each member is the spec's own phrase for it. That is what lets
    `checks/check_drift_audit.py` parse §11 item 3 out of the frozen document at run
    time and compare the two rosters **in both directions** without this module
    supplying the expected set — deriving the roster from the code and then
    proving the code covers it is circular and passes while measuring nothing.

    A seventh member would be an aggregate §11 item 3 does not name; a missing member
    is an aggregate §11 item 7 says to reconcile and this audit does not.
    """

    OPEN_MARGIN = "Σ open margin"
    RESERVATIONS = "Σ reservations"
    BUCKET_EXPOSURE = "bucket exposure"
    NET_LIQ_MARK = "net-liq mark"
    BALANCE = "balance"
    POSITION_TABLE = "per-position table"

    @property
    def unit(self) -> Unit:
        """Which floor governs this aggregate's drift. See `Unit`."""
        return Unit.COUNT if self is Aggregate.POSITION_TABLE else Unit.CURRENCY


# R0902 (too-many-instance-attributes) disabled for the two frozen records
# below: `ProjectedPosition` is `plane1_positions`' COLUMN LIST and
# `AggregateDrift` is one reconcile's full evidence. Neither has behaviour, and
# dropping a field to satisfy a count would drop either a schema column or a
# piece of the evidence a reader needs to act on the finding. The threshold is
# about behavioural classes accreting state.
# pylint: disable=too-many-instance-attributes
@dataclasses.dataclass(frozen=True)
class ProjectedPosition:
    """One row of `plane1_positions`, the Plane-1 log projection (§9).

    Mirrors the frozen schema's columns rather than the in-memory
    `seam.PositionRow`, because this is the GROUND-TRUTH side and it must not
    borrow the running side's shape. `databases/schema/plane1.sql` is the
    authority for every field name here.

    **THE MISSING COLUMN, STATED BECAUSE IT IS A FINDING AND NOT AN OVERSIGHT:**
    `plane1_positions` carries `avg_entry_price` and `stop_distance` and carries
    **no margin column at all**. Σ open margin's ground truth therefore cannot
    be read from the projection; it is RECONSTRUCTED as
    `qty_open × margin_per_contract[symbol]`. That is a real dependency on the
    margin cache and it is declared rather than hidden — see the module
    docstring's exception, and the report to the integrator.
    """

    trade_id: str
    strategy_id: str
    symbol: str
    side: str
    state: str
    qty_open: int
    qty_filled: int
    stop_distance: int
    last_event_id: int = 0

    @property
    def live(self) -> bool:
        """Is this row part of the open book? `closed` is history, not exposure."""
        return self.state in LIVE_PROJECTION_STATES


# R0903 (too-few-public-methods) disabled: each Protocol below declares exactly
# the surface the spec gives it — §7:501's formula, §12.10:737's one structured
# line, §12.5's one setter. A second verb would be a port doing two jobs, and
# `HaltSetterPort` carrying `clear` would let a drift audit clear a HALT.
# pylint: disable=too-few-public-methods
@runtime_checkable
class BucketPricerPort(Protocol):
    """§7:501's exposure formula, injected rather than imported.

    Injected so `nixrisk` takes no dependency on the allocator package, and two
    methods wide on purpose: an audit that also decided bucket membership would
    be a second authority on §7:498's static map.

    **`nixalloc.caps` does NOT satisfy this port as it stands, and saying so is
    the point.** It exposes `bucket_for(symbol)` — which matches — and
    `dollar_risk(exposure, config)`, which takes a `caps.Exposure` and a
    `caps.CapConfig` rather than the three plain values this port passes. Binding
    the config once and adapting the call is a ~10-line adapter and it is
    INTEGRATION work this branch does not do; claiming structural conformance
    that does not hold would be exactly the unverified assumption the port exists
    to avoid. Until that adapter is wired, a caller with no pricer gets
    `measurable=False` for bucket exposure, by name (§17).
    """

    def bucket_for(self, symbol: str) -> str | None:
        """§7:498's bucket for this symbol, or `None` if §7 places it in none."""

    def dollar_risk(self, symbol: str, contracts: int, stop_ticks: int) -> float:
        """§7:501's `(stop_ticks + slippage_pad) × tick_value × contracts`."""


@runtime_checkable
class Plane2Port(Protocol):
    """§12.10:737's operational plane. One structured line per event.

    Declared here rather than imported for the reason `nixrisk.halt` gives at
    its own copy: the risk path takes no dependency on the verifier package.
    Write-only by contract — this module never calls anything on it but `emit`.
    """

    def emit(self, event: str, **fields: Any) -> str:
        """Emit one structured operational line. The return is not consulted."""


@runtime_checkable
class HaltSetterPort(Protocol):
    """§12.5's setter surface, and the ONLY verb this audit is allowed.

    Structurally satisfied by `nixrisk.halt.HaltFlag`. Narrowed to `set` because
    §11 item 7 gives this audit exactly one authority — escalate material drift — and
    a port carrying `clear` would let a drift audit clear a HALT.
    """

    def set(self, cause: Any, reason: str, *, now: float | None = None) -> Any:
        """Declare a HALT under §12.5's cause. Audited on both planes by the flag."""


@dataclasses.dataclass(frozen=True)
class Running:
    """§11 item 3's running aggregates, as the Limiter holds them RIGHT NOW.

    `picture` carries the four the frozen `seam.FinancialPicture` publishes.
    The other two are separate, optional fields and NOT invented defaults:

      * `net_liq_mark` — §11 item 3 names it; the frozen snapshot does not carry it
        (`nixrisk.survival` holds it). `None` ⇒ the aggregate is unmeasurable
        and is reported by name, never scored zero-drift.
      * `bucket_exposure` — likewise, priced by `nixalloc.caps` and held by the
        Allocator. `None` ⇒ unmeasurable, reported by name.

    A `0.0` default on either would be the fail-open the seam's `stop_distance`
    field already records (D3.136): it would read as "measured, and they agree".
    """

    picture: FinancialPicture
    net_liq_mark: float | None = None
    bucket_exposure: Mapping[str, float] | None = None


@dataclasses.dataclass(frozen=True)
class GroundTruth:
    """§11 item 7's *ground truth*: the Plane-1 log projection plus a broker poll.

    `projection` is `plane1_positions` as it currently stands. `broker` is one
    `seam.BrokerTruth` poll — balance and positions pulled together, per §4's
    rule that a balance read at one instant against positions read at another is
    the stale-balance tear §3's atomicity exists to prevent.

    `net_liq` and `reservations_scanned` are separate and optional for the same
    §17 reason `Running`'s two optional fields are: `BrokerTruth` carries no
    net-liq figure, and Σ reservations' ground truth is the reservation ledger's
    own full scan (`reservations.LedgerAudit.scanned`), which lives in the
    Limiter's memory and not in the projection. Absent ⇒ named unmeasurable.
    """

    projection: tuple[ProjectedPosition, ...]
    broker: BrokerTruth
    net_liq: float | None = None
    reservations_scanned: float | None = None
    scanned_at: float = 0.0


@dataclasses.dataclass(frozen=True)
class AggregateDrift:
    """One aggregate's reconcile. Evidence, never a bare verdict.

    `drift` is signed and is always `running - scanned`, so a negative figure
    means the incremental aggregate UNDER-counts — which is the direction that
    lets §3 Phase B approve orders against capital that is already spent, and is
    therefore the direction a reader needs to be able to see at a glance.
    """

    aggregate: Aggregate
    running: float | None
    scanned: float | None
    drift: float
    drifted: bool
    material: bool
    detail: str
    measurable: bool = True
    unmeasurable_reason: str = ""

    @property
    def unit(self) -> Unit:
        """Delegated so the unit is decided in exactly one place."""
        return self.aggregate.unit

    def as_fields(self) -> dict[str, str]:
        """The Plane-1 / Plane-2 field map for this reading. All values `str`."""
        return {
            "aggregate": self.aggregate.name.lower(),
            "spec_phrase": self.aggregate.value,
            "unit": self.unit.value,
            "running": repr(self.running),
            "scanned": repr(self.scanned),
            "drift": repr(self.drift),
            "material": repr(self.material),
            "noise_floor": repr(NOISE_FLOOR),
            "material_floor": repr(MATERIAL_FLOOR),
            "detail": self.detail,
        }


def _is_material(reading: AggregateDrift) -> bool:
    """`reading.material`, behind an ANNOTATED parameter. Not a stylistic choice.

    Written as a predicate rather than inlined into the two comprehensions that
    need it because a comprehension variable has no type a static reader can
    resolve, and `checks/check_uncalled_entry_points.py` resolves a call site by
    the RECEIVER'S TYPE. With an unresolvable receiver, `r.material` is credited
    to every class in the tree carrying a public `material` — which measurably
    moved `reservations.py::LedgerAudit.material` out of that gate's uncalled
    baseline and produced an acquired-coverage FAIL in a module this one does not
    touch. An annotated parameter makes the receiver `AggregateDrift` and the
    attribution correct. A module must not change the population a different
    instrument is measuring.
    """
    return reading.material


@dataclasses.dataclass(frozen=True)
class AuditOutcome:
    """What one full scan found, and what it did about it.

    `complete` is False whenever ANY §11 item 3 aggregate could not be scanned. A
    caller that reads `clean` without reading `complete` would treat "five of six
    agree and the sixth was never looked at" as a healthy book, which is the
    §17 failure this audit is built to refuse.
    """

    at: float
    readings: tuple[AggregateDrift, ...]
    halted: bool
    halt_reason: str
    plane1_rows: int
    plane2_lines: int

    @property
    def drifted(self) -> tuple[AggregateDrift, ...]:
        """Every aggregate whose disagreement cleared the noise floor."""
        return tuple(r for r in self.readings if r.drifted)

    @property
    def material(self) -> tuple[AggregateDrift, ...]:
        """Every aggregate whose drift is at least one whole commitment."""
        return tuple(filter(_is_material, self.readings))

    @property
    def unmeasurable(self) -> tuple[AggregateDrift, ...]:
        """Every §11 item 3 aggregate this scan could not look at, named."""
        return tuple(r for r in self.readings if not r.measurable)

    @property
    def complete(self) -> bool:
        """Was every §11 item 3 aggregate actually reconciled?"""
        return not self.unmeasurable

    @property
    def clean(self) -> bool:
        """Complete AND no drift. Both halves, deliberately."""
        return self.complete and not self.drifted


# ---------------------------------------------------------------------------
# CLASSIFICATION — the band, applied in exactly one place
# ---------------------------------------------------------------------------


def classify(drift: float, unit: Unit) -> tuple[bool, bool]:
    """`(drifted, material)` for one signed drift. The band, spelled once.

    Written as a free function rather than a method so the gate can drive the
    band directly at its edges — `check_drift_audit` asserts both sides of
    `MATERIAL_FLOOR`, and a threshold tested on one side is not tested.
    """
    if unit is Unit.COUNT:
        # Exact arithmetic ⇒ no noise floor, and any difference is a whole
        # position. See the module docstring.
        real = drift != 0.0
        return (real, real)
    magnitude = abs(drift)
    if magnitude <= NOISE_FLOOR:
        return (False, False)
    return (True, magnitude >= MATERIAL_FLOOR)


def _unusable(name: str, value: float) -> str:
    """`""` when `value` is a real number, else why it cannot be reconciled."""
    if math.isnan(value) or math.isinf(value):
        return (
            f"{name} is {value!r} — a drift computed from NaN/Inf cannot be "
            "compared against any floor, and a safety property that cannot be "
            "evaluated is not proven (nix_check_contract.md §17)"
        )
    return ""


def _unmeasured(aggregate: Aggregate, why: str) -> AggregateDrift:
    """The §17 answer: named, not scored zero."""
    return AggregateDrift(
        aggregate=aggregate,
        running=None,
        scanned=None,
        drift=0.0,
        drifted=False,
        material=False,
        detail=f"{aggregate.value}: NOT RECONCILED — {why}",
        measurable=False,
        unmeasurable_reason=why,
    )


def _currency(
    aggregate: Aggregate, running: float | None, scanned: float | None, note: str
) -> AggregateDrift:
    """One currency-valued reconcile, with both §17 guards applied."""
    if running is None:
        return _unmeasured(
            aggregate,
            "no running value was supplied. §11 item 3 names this aggregate but the "
            "frozen FinancialPicture does not carry it, so it must be passed in "
            "explicitly; a default would read as 'measured, and they agree'",
        )
    if scanned is None:
        return _unmeasured(
            aggregate,
            "no ground truth was supplied — the full scan had nothing to "
            "reconcile against, which is not the same fact as agreement",
        )
    for name, value in (("running", running), ("scanned", scanned)):
        complaint = _unusable(f"{aggregate.value} {name}", value)
        if complaint:
            return _unmeasured(aggregate, complaint)
    drift = running - scanned
    drifted, material = classify(drift, aggregate.unit)
    verdict = "MATERIAL" if material else ("drift" if drifted else "agrees")
    return AggregateDrift(
        aggregate=aggregate,
        running=running,
        scanned=scanned,
        drift=drift,
        drifted=drifted,
        material=material,
        detail=(
            f"{aggregate.value}: running {running!r} vs full scan {scanned!r} "
            f"⇒ drift {drift:+.9g} ({verdict}); {note}"
        ),
    )


# ---------------------------------------------------------------------------
# THE FULL SCAN — one function per aggregate, none of them reading the others
# ---------------------------------------------------------------------------


def _scan_open_margin(running: Running, truth: GroundTruth) -> AggregateDrift:
    """Σ open margin: the projection's contract counts at the cache's prices."""
    prices = running.picture.margin_per_contract
    missing = sorted(
        {
            row.symbol
            for row in truth.projection
            if row.live and row.symbol not in prices
        }
    )
    if missing:
        return _unmeasured(
            Aggregate.OPEN_MARGIN,
            f"the margin cache prices no contract for {', '.join(missing)}, and "
            "plane1_positions carries no margin column of its own — so the "
            "ground truth for these rows cannot be reconstructed at all",
        )
    scanned = math.fsum(
        float(row.qty_open) * float(prices[row.symbol])
        for row in truth.projection
        if row.live
    )
    live = sum(1 for row in truth.projection if row.live)
    return _currency(
        Aggregate.OPEN_MARGIN,
        running.picture.sum_open_margin,
        scanned,
        f"scan over {live} live projection row(s), priced from the margin cache "
        f"(plane1_positions has no margin column — see ProjectedPosition)",
    )


def _scan_reservations(running: Running, truth: GroundTruth) -> AggregateDrift:
    """Σ reservations: the ledger's own full scan of its TAKEN rows."""
    return _currency(
        Aggregate.RESERVATIONS,
        running.picture.sum_reservations,
        truth.reservations_scanned,
        "ground truth is reservations.LedgerAudit.scanned — an fsum over the "
        "TAKEN rows, produced by different arithmetic than the running Σ",
    )


def _scan_balance(running: Running, truth: GroundTruth) -> AggregateDrift:
    """Balance: the running snapshot against the broker's own answer (§4)."""
    return _currency(
        Aggregate.BALANCE,
        running.picture.balance,
        truth.broker.balance,
        f"ground truth is the broker poll taken at {truth.broker.polled_at!r} "
        "(§4: balance and positions pulled in ONE motion)",
    )


def _scan_net_liq(running: Running, truth: GroundTruth) -> AggregateDrift:
    """Net-liq mark: the running mark against the broker's net-liq (§6.5)."""
    return _currency(
        Aggregate.NET_LIQ_MARK,
        running.net_liq_mark,
        truth.net_liq,
        "net-liq, never cash — §15 C2 keeps them separate because the broker "
        "liquidates on net-liq while sizing is computed on cash",
    )


def _scan_buckets(
    running: Running, truth: GroundTruth, pricer: BucketPricerPort | None
) -> AggregateDrift:
    """Bucket exposure: §7:501's formula over the projection, per bucket.

    The reported drift is the LARGEST absolute per-bucket disagreement, and the
    detail names the bucket that produced it. A sum over buckets would let a
    positive drift in one cancel a negative drift in another, which is exactly
    how a concentration defect hides.
    """
    if running.bucket_exposure is None:
        return _unmeasured(
            Aggregate.BUCKET_EXPOSURE,
            "no running bucket exposure was supplied. §11 item 3 names it but the "
            "frozen FinancialPicture does not carry it (nixalloc.caps prices it "
            "and the Allocator holds it), so it must be passed in explicitly",
        )
    if pricer is None:
        return _unmeasured(
            Aggregate.BUCKET_EXPOSURE,
            "no BucketPricerPort was supplied, so §7:501's formula cannot be "
            "applied to the projection and there is no ground truth to compare",
        )
    scanned: dict[str, float] = {}
    for row in truth.projection:
        if not row.live:
            continue
        bucket = pricer.bucket_for(row.symbol)
        if bucket is None:
            # §7:498 places some symbols in no bucket. That is a real answer and
            # not an error: a symbol with no bucket has no within-bucket
            # concentration to measure. It contributes to no bucket's Σ.
            continue
        scanned[bucket] = scanned.get(bucket, 0.0) + pricer.dollar_risk(
            row.symbol, row.qty_open, row.stop_distance
        )
    # Bound to a local AFTER the None guard above. `running.bucket_exposure` is
    # `Mapping[str, float] | None`, and a narrowing does not survive into the
    # `key=` lambda below — mypy is right about that and the repair is a local,
    # not a cast.
    held: Mapping[str, float] = running.bucket_exposure
    buckets = sorted(set(scanned) | set(held))
    if not buckets:
        return _currency(
            Aggregate.BUCKET_EXPOSURE,
            0.0,
            0.0,
            "no bucketed exposure on either side — an empty book agrees "
            "trivially and this reading carries no discriminating power",
        )
    worst = max(
        buckets,
        key=lambda b: abs(float(held.get(b, 0.0)) - scanned.get(b, 0.0)),
    )
    return _currency(
        Aggregate.BUCKET_EXPOSURE,
        float(held.get(worst, 0.0)),
        scanned.get(worst, 0.0),
        f"worst of {len(buckets)} bucket(s) is {worst!r}; §7:501 priced over the "
        "projection by the injected pricer, per bucket and never summed across "
        "them (a cross-bucket sum lets one bucket's drift cancel another's)",
    )


def _position_divergences(
    picture_rows: Sequence[PositionRow], projection: Sequence[ProjectedPosition]
) -> list[str]:
    """Every way the two position tables disagree, each named by trade_id."""
    running_live: dict[str, PositionRow] = {
        row.trade_id: row
        for row in picture_rows
        if getattr(row.state, "value", str(row.state)) != "closed"
    }
    scanned_live: dict[str, ProjectedPosition] = {
        row.trade_id: row for row in projection if row.live
    }
    problems: list[str] = []
    for trade_id in sorted(set(running_live) - set(scanned_live)):
        row = running_live[trade_id]
        problems.append(
            f"{trade_id}: held by the running table ({row.symbol}, size "
            f"{row.size}) and ABSENT from the projection — a position the log "
            "does not know about"
        )
    for trade_id in sorted(set(scanned_live) - set(running_live)):
        # A DIFFERENT name from the loop above: that one binds a `PositionRow`
        # and this one a `ProjectedPosition`. They are the two sides of the
        # reconcile and giving them one name is how the sides get confused.
        logged_only = scanned_live[trade_id]
        problems.append(
            f"{trade_id}: in the projection ({logged_only.symbol}, qty_open "
            f"{logged_only.qty_open}) and ABSENT from the running table — an open "
            "position the Limiter is no longer tracking"
        )
    for trade_id in sorted(set(running_live) & set(scanned_live)):
        held = running_live[trade_id]
        logged = scanned_live[trade_id]
        if abs(held.size) != logged.qty_open:
            problems.append(
                f"{trade_id}: size {held.size} held vs qty_open "
                f"{logged.qty_open} in the projection"
            )
        if held.symbol != logged.symbol:
            problems.append(
                f"{trade_id}: symbol {held.symbol!r} held vs {logged.symbol!r} "
                "in the projection"
            )
        if held.strategy_id != logged.strategy_id:
            problems.append(
                f"{trade_id}: strategy_id {held.strategy_id!r} held vs "
                f"{logged.strategy_id!r} in the projection"
            )
    return problems


def _scan_position_table(running: Running, truth: GroundTruth) -> AggregateDrift:
    """The per-position table, row by row. Counts, so no noise floor (see `Unit`)."""
    problems = _position_divergences(running.picture.positions, truth.projection)
    drift = float(len(problems))
    drifted, material = classify(drift, Unit.COUNT)
    held = len(running.picture.positions)
    logged = sum(1 for row in truth.projection if row.live)
    body = "; ".join(problems) if problems else "every live row agrees"
    return AggregateDrift(
        aggregate=Aggregate.POSITION_TABLE,
        running=float(held),
        scanned=float(logged),
        drift=drift,
        drifted=drifted,
        material=material,
        detail=(
            f"per-position table: {held} row(s) held vs {logged} live projection "
            f"row(s); {len(problems)} divergence(s) — {body}"
        ),
    )


def full_scan(
    running: Running, truth: GroundTruth, *, pricer: BucketPricerPort | None = None
) -> tuple[AggregateDrift, ...]:
    """§11 item 7's reconcile of EVERY §11 item 3 running aggregate. Pure — no side effects.

    Returns one `AggregateDrift` per `Aggregate` member, in declaration order,
    always. A reconcile that silently dropped an aggregate it could not scan
    would report a shorter, cleaner-looking tuple; every member is present and
    an unscannable one carries `measurable=False` and says why.
    """
    return (
        _scan_open_margin(running, truth),
        _scan_reservations(running, truth),
        _scan_buckets(running, truth, pricer),
        _scan_net_liq(running, truth),
        _scan_balance(running, truth),
        _scan_position_table(running, truth),
    )


# ---------------------------------------------------------------------------
# THE AUDIT — the scan, the two planes, and §12.5's setter
# ---------------------------------------------------------------------------


class DriftAudit:  # pylint: disable=too-many-instance-attributes
    """§11 item 7's periodic full-scan audit, wired to both planes and to §12.5.

    **All three collaborators are REQUIRED.** An audit constructed without a
    HALT setter would find material drift, write a row saying so, and leave money
    flowing — D3.178's shape (a verb nobody calls) inside the fix for it. Making
    the wiring defect impossible at construction is cheaper than a gate that
    catches it later (directive 8).
    """

    def __init__(
        self,
        *,
        plane1: Any,
        plane2: Plane2Port,
        halt: HaltSetterPort,
        interval_s: float,
        clock: Callable[[], float] = time.time,
    ) -> None:
        """§12A-shaped boot validation on the one tunable, at construction."""
        if not isinstance(interval_s, (int, float)) or isinstance(interval_s, bool):
            raise KnobError(
                f"interval_s must be a number, got {interval_s!r} — §12A knobs "
                "are validated at boot, never at first use"
            )
        if math.isnan(interval_s) or interval_s < MIN_INTERVAL_S:
            raise KnobError(
                f"interval_s {interval_s!r} is below the floor {MIN_INTERVAL_S!r}: "
                "§11 makes the entry pathway cache-reads-and-arithmetic only, and "
                "an unbounded-frequency full scan is the hot-path cost §11 item 7 is "
                "explicitly scheduled OFF the hot path to avoid"
            )
        self._plane1 = plane1
        self._plane2 = plane2
        self._halt = halt
        self._interval_s = float(interval_s)
        self._clock = clock
        self._last_run: float | None = None

    # -- §11 item 7's "periodic" ------------------------------------------------

    @property
    def interval_s(self) -> float:
        """The configured period. §11 item 7 says *periodic*; this is the period."""
        return self._interval_s

    @property
    def last_run(self) -> float | None:
        """When the last full scan ran, or `None` if none has. Never invented."""
        return self._last_run

    def due(self, now: float | None = None) -> bool:
        """Is a full scan due? The first call is always due — never scanned yet."""
        stamp = self._clock() if now is None else now
        if self._last_run is None:
            return True
        return stamp - self._last_run >= self._interval_s

    def run_if_due(
        self,
        running: Running,
        truth: GroundTruth,
        *,
        pricer: BucketPricerPort | None = None,
        now: float | None = None,
    ) -> AuditOutcome | None:
        """`run` when due, else `None`. `None` is 'not yet', never 'clean'."""
        stamp = self._clock() if now is None else now
        if not self.due(stamp):
            return None
        return self.run(running, truth, pricer=pricer, now=stamp)

    # -- the audit itself --------------------------------------------------

    def run(
        self,
        running: Running,
        truth: GroundTruth,
        *,
        pricer: BucketPricerPort | None = None,
        now: float | None = None,
    ) -> AuditOutcome:
        """One full scan: reconcile, escalate, record. In that order, deliberately.

        Order of operations, each step chosen for the failure it survives:

        1. **the scan**, which touches nothing;
        2. **the HALT**, if any drift is material — money is gated from this
           instant, BEFORE any log write. An audit that wrote six rows and then
           halted would leave money flowing for the duration of the write, which
           inverts the priority `nixrisk.halt` already fixes one level down;
        3. **the Plane-1 rows**, one per drifted aggregate, so *which* aggregate
           drifted is an indexed query on `event_type` and not a JSON parse;
        4. **the Plane-2 lines**, including one per aggregate that could NOT be
           scanned — those get no Plane-1 row (they are diagnostics, not money
           transitions) but they must not be silent (§17).

        A clean, complete scan writes to NEITHER plane: §11 item 7 says *drift ⇒ audit
        event*, and a clean scan is not an event. See the module docstring's
        liveness non-claim for what that costs.
        """
        stamp = self._clock() if now is None else now
        readings = full_scan(running, truth, pricer=pricer)
        self._last_run = stamp

        material = list(filter(_is_material, readings))
        halt_reason = ""
        if material:
            halt_reason = (
                "§11 item 7 full-scan audit: MATERIAL drift in "
                f"{len(material)} of {len(readings)} running aggregate(s) — "
                + "; ".join(
                    f"{r.aggregate.value} {r.drift:+.9g}"
                    f" ({r.unit.value}, floor {MATERIAL_FLOOR!r})"
                    for r in material
                )
            )
            self._halt.set(CAUSE, halt_reason, now=stamp)

        rows = 0
        lines = 0
        for reading in readings:
            if not reading.drifted:
                continue
            fields = reading.as_fields()
            fields["halted"] = repr(bool(material))
            self._plane1.enqueue(
                EventRow(
                    kind=EventKind.DRIFT_AUDIT,
                    ts=stamp,
                    strategy_id=_actor(reading, running),
                    reason=reading.detail,
                    fields=fields,
                )
            )
            rows += 1
            self._plane2.emit(PLANE2_EVENT, **fields)
            lines += 1

        for reading in readings:
            if reading.measurable:
                continue
            self._plane2.emit(
                PLANE2_INCOMPLETE_EVENT,
                aggregate=reading.aggregate.name.lower(),
                spec_phrase=reading.aggregate.value,
                reason=reading.unmeasurable_reason,
            )
            lines += 1

        return AuditOutcome(
            at=stamp,
            readings=readings,
            halted=bool(material),
            halt_reason=halt_reason,
            plane1_rows=rows,
            plane2_lines=lines,
        )


#: §9:553 requires `strategy_id` on every row and `plane1.sql` forbids the empty
#: string. A drift audit is a system-wide reconcile that belongs to no strategy,
#: so it carries the same sentinel `nixrisk.halt` and `nixrisk.coldstart` use —
#: attributing a system audit to whichever strategy happened to be running would
#: be worse than no attribution.
SYSTEM_ACTOR: Final[str] = "__system__"


def _actor(reading: AggregateDrift, running: Running) -> str:
    """Whose row is this? The system's, unless exactly one strategy is exposed.

    Deliberately conservative: a per-position divergence naming one strategy is
    attributable, everything else is the system's. Guessing an owner for a
    balance drift would put a false name in the money log.
    """
    if reading.aggregate is not Aggregate.POSITION_TABLE:
        return SYSTEM_ACTOR
    owners = {row.strategy_id for row in running.picture.positions}
    return owners.pop() if len(owners) == 1 else SYSTEM_ACTOR


def projection_from_rows(
    rows: Iterable[Mapping[str, Any]],
) -> tuple[ProjectedPosition, ...]:
    """Build the ground-truth side from `plane1_positions` rows as read.

    Column names are `plane1_positions`' own, so a schema rename breaks here
    loudly rather than producing an empty projection that agrees with an empty
    book. There is no `.get(..., default)` anywhere in this function for exactly
    that reason.
    """
    return tuple(
        ProjectedPosition(
            trade_id=str(row["trade_id"]),
            strategy_id=str(row["strategy_id"]),
            symbol=str(row["symbol"]),
            side=str(row["side"]),
            state=str(row["state"]),
            qty_open=int(row["qty_open"]),
            qty_filled=int(row["qty_filled"]),
            stop_distance=int(float(row["stop_distance"] or 0)),
            last_event_id=int(row["last_event_id"]),
        )
        for row in rows
    )
