"""§6.6's realized-P&L EMA — the ONE place in the system a score is computed.

Authority: `docs/nics_risk_subsystem_spec_v1.3.md` §6.6:429-472 (*Performance-
weighted contention*), §12A:836 (`SCORE_EMA_SPAN_DAYS`), §11 (hot-path rules),
§12.10 / §9 (the Plane-1 record this reads). ARC 036 sub-agent A.

§6.6's measurement clause, and every word of it is a constraint this module is
accountable to:

  * **Realized P&L only** — closed trades. *"Unrealized/paper gains never steer
    capital (a green open position can reverse before it closes)."*
  * **Advances per DAY** — *"one realized number per symbol per day (keeps
    symbols comparable; a hyperactive symbol can't dominate purely by trading
    more often)."*
  * **EMA-smoothed** — *"recent days weighted more, older days fade continuously
    (no hard week/older cliff)."*
  * **Span = `SCORE_EMA_SPAN_DAYS`, default 10 trading days, tunable —
    "calibrated on the box once real realized data exists; NOT a carved
    constant."**

------------------------------------------------------------------------------
THE INPUT DOES NOT EXIST YET, AND THAT IS MEASURED RATHER THAN ASSUMED
------------------------------------------------------------------------------
The brief that commissioned this module says it *"reads closed-trade realized
P&L from Plane-1"*. **Plane-1 carries no realized P&L today.** Measured this
arc, against the frozen artifacts:

  * `databases/schema/plane1.sql` (frozen ARC 035 Phase 0.4) gives
    `plane1_event_log` nine columns and none of them is a money figure; the only
    place a number could live is the free-form `payload JSONB`.
  * `plane1_positions` has `qty_*`, `avg_entry_price` and `stop_distance` — no
    realized column, by design: §9's projection records *what is*, not what was
    earned.
  * Nothing in `scripts/` writes a realized figure into any payload. The one
    realized-P&L hand-off that exists is `nixrisk.flatten.ScoringSink.
    book_realized`, which carries a BALANCE DELTA over a set of closed trades
    (`flatten.py:650`) — an account-level number that is not attributed to a
    `(strategy_id, symbol)` pair and therefore cannot key §6.6's row.
  * CHECK-DEBT D3.213 records that Plane 1 is BUILT AND NOT WIRED, and
    `nixrisk.seam.EventKind` cannot emit `filled` at all.

So this module declares the payload key it reads — `REALIZED_FIELD` — and
**REFUSES a realizing event that does not carry it** (`MissingRealized`). That
refusal is the load-bearing decision in the file. The tempting alternative is to
treat an absent figure as a zero advance; it would make every pair in a real log
score exactly 0.0, every comparison a tie, and every tie an FCFS fallback that
looks *precisely* like a healthy cold start. The engine would be totally blind
and every gate over it green. Fail closed and loud (CLAUDE.md directive 4).

------------------------------------------------------------------------------
UNREALIZED CANNOT REACH THE NUMBER BY ANY PATH, AND THE PATHS ARE ENUMERATED
------------------------------------------------------------------------------
Two doors, both shut and both driven by `checks/check_scoring_ema.py`:

 1. **By event type.** `REALIZING_EVENT_TYPES` is the set of `plane1_event_enum`
    members that book a realization. `NON_REALIZING_EVENT_TYPES` is *every other
    member*, ENUMERATED — the two are asserted to partition the enum, so a type
    added to the schema by a later arc is a loud miss here rather than a silent
    default. A `filled` row is an OPEN position and is refused, not ignored:
    ignoring it would make "the engine never saw an open mark" and "the engine
    saw one and dropped it" the same observation.
 2. **By field name.** A realizing event whose payload also carries an
    unrealized figure (`BANNED_UNREALIZED_FIELDS`) is refused whole. A payload
    carrying both a realized and a mark-to-market number is an invitation for
    the next reader to take the wrong one, and the wrong one is the one §6.6
    spent a sentence forbidding.

------------------------------------------------------------------------------
A DAY WITH NO CLOSED TRADES IS A **ZERO ADVANCE**, NOT AN ABSENT DAY
------------------------------------------------------------------------------
Both are defensible; this is the choice and this is why. §6.6 requires older
days to *"fade continuously"*. If absent days were skipped, the EMA would step
only when a trade closed — so a pair that realized $5,000 once and has closed
nothing for a month would carry the identical score to a pair that realized
$5,000 yesterday. Stale performance would keep steering capital forever, and the
"recent days weighted more" clause would be false: recency would be measured in
TRADES, not in days, which is the exact axis §6.6's per-day reduction exists to
remove.

So the smoothing walks a **day grid** from the pair's first realized day to the
as-of day, folding a zero on every day the pair closed nothing.
`test_check_scoring_ema.py` drives the consequence: a silent pair decays toward
zero, and the decay rate is the span's.

**The grid is TRADING days, not calendar days**, because §6.6 says *"10 trading
days (~2 weeks)"* and those are different quantities: a calendar-day walk would
fold two extra zeros every weekend and make a 10-trading-day span behave like
about seven. `is_trading_day` is the default grid — Monday to Friday — and it is
INJECTABLE, because the honest state of the tree is that **no session-calendar
module is authored** (CLAUDE.md's spec table lists it under *not yet authored*),
so exchange holidays are NOT excluded. That is a real inaccuracy of a few days a
year, it is recorded as CHECK-DEBT, and it is a parameter rather than a literal
so the calendar replaces it without touching this arithmetic.

A realized close stamped on a day the grid excludes is REFUSED by name rather
than silently dropped: a Saturday `closed` row means either the grid is wrong or
the record is, and both are findings.

------------------------------------------------------------------------------
THIN DATA: THE ENGINE CLAIMS NOTHING IT HAS NOT MEASURED
------------------------------------------------------------------------------
§6.6's own caution: *"early realized samples are thin — a handful of closed
trades per symbol per day — so the number matters less than accumulating enough
history to trust it."*

There is no bias correction here and that is deliberate. A one-day EMA IS that
day's advance; dressing it up as a converged average would manufacture exactly
the confidence §6.6 warns is absent. Instead `PairScore` carries
`days_observed` (days with at least one REAL realized close — never the calendar
span, which would count silence as evidence) and `closes_observed`, and the seam
carries `days_observed` onto the wire so a consumer can read how much history
stands behind a rank. **Nothing here branches on it**: what to DO about a thin
score is the Allocator's policy, and deciding it in the scorer would put the
allocation judgment in two places.

------------------------------------------------------------------------------
THE SPAN IS DERIVED, NEVER CARVED — AND THERE IS NO RELOAD VERB
------------------------------------------------------------------------------
`RealizedEmaEngine.from_config` reads `risks/scoring.config.json` through
`risk_config.load_risk_configs`, which validates it (`positive.scalars`,
`scoring.span_is_whole_days`). There is no default span in this module and no
`span_days=10` anywhere in it; `check_scoring_ema` reads this file's AST and
reddens on a numeric literal bound to a span-shaped name.

§12.11 is boot-loaded, restart-only. The engine takes its span at construction
and holds it on a frozen instance attribute; there is no method here that
re-reads a file, watches a path or reads an mtime. The only way to observe a
changed span is to be a new process, and `test_check_scoring_ema.py` proves that
the only way it can be proven — by editing the config under a LIVE process,
observing no change, killing it, and observing the change in its successor.

------------------------------------------------------------------------------
WHAT THIS MODULE DOES NOT DO
------------------------------------------------------------------------------
* It does not publish. `seam.RankingPublisher` is the publish side and the
  Scoring PROCESS that drives it is sub-agent C's.
* It does not read a database. Every function here is pure over rows a caller
  supplies, so the fold can be driven without Postgres — the same separation
  `nixrisk.projection.fold_events` makes, for the same reason.
* It does not implement DSR, band membership, promotion, or anything else from
  the Gate 5/6/7 offline evaluator. §6.6 Scoring is the runtime contention EMA
  and is a different object (CHECK-DEBT D3.215).
* **It runs nowhere.** No daemon in this tree constructs a `RealizedEmaEngine`,
  because there is no Scoring daemon; and its input field is written by nothing.
  No green in this module may be read as saying a score is being computed in
  production.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from nixscore.seam import PairKey, RankingSnapshot, RankRow, rank_rows

#: The `risks/` module and knob §12A:836 names. Read through `risk_config`, so
#: the value here is a NAME and never a number.
SPAN_MODULE: Final[str] = "scoring"
SPAN_KEY: Final[str] = "score_ema_span_days"

#: The `plane1_event_log.payload` key this engine reads a realization from.
#: NOTHING IN THIS TREE WRITES IT — see the module docstring. Declared so the
#: writer that eventually does has one name to write, and so the refusal below
#: can say what was missing rather than that something was.
REALIZED_FIELD: Final[str] = "realized_pnl"

#: Payload keys that name an OPEN mark. Their presence on a realizing event is
#: refused whole (§6.6: unrealized never steers capital).
BANNED_UNREALIZED_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "unrealized_pnl",
        "unrealized",
        "open_pnl",
        "mark_to_market",
        "mtm",
        "paper_pnl",
        "floating_pnl",
    }
)

#: `plane1_event_enum` members that BOOK a realization — the round trip, or a
#: leg of it, actually came off. `closed` is §9's terminal round trip;
#: `protective_exit` and `sentinel_flatten` may be scale-outs and realize the
#: part they took off.
REALIZING_EVENT_TYPES: Final[frozenset[str]] = frozenset(
    {"closed", "protective_exit", "sentinel_flatten"}
)

#: EVERY other `plane1_event_enum` member, enumerated rather than defaulted.
#: `filled` heads the list and is the whole point: it is an OPEN position, its
#: P&L is a mark, and §6.6 forbids a mark from steering capital.
NON_REALIZING_EVENT_TYPES: Final[frozenset[str]] = frozenset(
    {
        "filled",
        "signal",
        "accepted",
        "denied",
        "exit_intent",
        "cancel",
        "reservation_taken",
        "reservation_released",
        "go_timeout",
        "drift_audit",
        "halt_set",
        "halt_cleared",
        "operator_action",
        "strategy_lifecycle",
        "cold_start_outcome",
    }
)

#: The two sets together. `check_scoring_ema` compares this against the SCHEMA's
#: own enum in both directions, so a type added by a later arc is a loud miss.
CLASSIFIED_EVENT_TYPES: Final[frozenset[str]] = (
    REALIZING_EVENT_TYPES | NON_REALIZING_EVENT_TYPES
)

#: §9's documented "this event has no trade" sentinel.
NO_TRADE: Final[str] = "-"

_ONE_DAY: Final[dt.timedelta] = dt.timedelta(days=1)

#: A hard ceiling on the day walk. Not a tuning knob: it is the difference
#: between a mis-stamped `occurred_at` (a 1970 epoch date is the classic one)
#: producing a loud refusal and it producing a twenty-thousand-iteration loop
#: nobody attributes. Off the hot path either way — this runs in the Scoring
#: process, never in the Allocator or the Limiter.
MAX_GRID_DAYS: Final[int] = 4000


class EmaError(RuntimeError):
    """A realized-P&L fold that cannot be performed. Never degraded to a zero."""


class UnrealizedLeak(EmaError):
    """An OPEN or unrealized figure reached the realized fold. §6.6's one ban."""


class MissingRealized(EmaError):
    """A realizing event carried no realized figure. Refused, never defaulted."""


# ---------------------------------------------------------------------------
# The day grid
# ---------------------------------------------------------------------------


def is_trading_day(day: dt.date) -> bool:
    """Monday-to-Friday. The DEFAULT grid, and an approximation that says so.

    Exchange holidays are NOT excluded, because no session-calendar module is
    authored in this tree. Injectable everywhere it is used, so the real
    calendar replaces it without touching the smoothing arithmetic.
    """
    return day.weekday() < 5


def trading_day(value: Any) -> dt.date:
    """The UTC calendar date of one `occurred_at`, from date, datetime or text.

    Timezone-aware datetimes are converted to UTC first; a naive one is READ as
    UTC rather than as local time, because `plane1_event_log.occurred_at` is
    `TIMESTAMPTZ` and a local reading would move a late-session close into the
    next day on one box and not on another.
    """
    if isinstance(value, dt.datetime):
        aware = value if value.tzinfo else value.replace(tzinfo=dt.UTC)
        return aware.astimezone(dt.UTC).date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        return _day_from_text(value)
    raise EmaError(
        f"cannot read a trading day from {value!r} of type {type(value).__name__}; "
        "the EMA's unit is a DAY (§6.6:438) and an unreadable stamp cannot be "
        "assigned to one"
    )


def _day_from_text(value: str) -> dt.date:
    """One ISO timestamp or date as a UTC date. Raises rather than guessing."""
    text = value.strip()
    try:
        return trading_day(dt.datetime.fromisoformat(text))
    except ValueError:
        pass
    try:
        return dt.date.fromisoformat(text[:10])
    except ValueError as exc:
        raise EmaError(f"{value!r} is not an ISO date or timestamp: {exc}") from exc


# ---------------------------------------------------------------------------
# What the fold reads
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class RealizedClose:
    """One realization, attributed to a pair and a day. Immutable."""

    strategy_id: str
    symbol: str
    day: dt.date
    realized: float
    event_type: str
    trade_id: str

    @property
    def key(self) -> PairKey:
        """§6.6's locked canonical key: `(strategy_id, symbol)`."""
        return (self.strategy_id, self.symbol)


@dataclasses.dataclass(frozen=True, slots=True)
class PairScore:
    """One pair's EMA and the honest account of what stands behind it.

    `days_observed` counts days with at least one REAL realized close. It is
    deliberately not the calendar span from `first_day` to `through`: that would
    count silence as evidence, and §6.6's caution is about how thin the real
    samples are.
    """

    realized_ema: float
    days_observed: int
    closes_observed: int
    first_day: dt.date
    last_day: dt.date
    through: dt.date
    span_days: int

    @property
    def key_facts(self) -> str:
        """A one-line account of the evidence, for a check's `evidence` field."""
        return (
            f"ema={self.realized_ema:.6f} over span {self.span_days}d from "
            f"{self.closes_observed} close(s) on {self.days_observed} realized "
            f"day(s) between {self.first_day} and {self.last_day}, "
            f"as of {self.through}"
        )


# ---------------------------------------------------------------------------
# Extraction — the two doors unrealized would come through
# ---------------------------------------------------------------------------


def _realized_amount(payload: Mapping[str, Any], where: str) -> float:
    """The realized figure, or a refusal naming which door was open."""
    leaked = sorted(BANNED_UNREALIZED_FIELDS & set(payload))
    if leaked:
        raise UnrealizedLeak(
            f"{where}: payload carries {', '.join(leaked)} — an OPEN mark on a "
            "realizing event. §6.6: 'Unrealized/paper gains never steer capital "
            "(a green open position can reverse before it closes).' The row is "
            "refused whole rather than read past, because a payload carrying "
            "both figures is one field name away from steering capital on the "
            "wrong one"
        )
    if REALIZED_FIELD not in payload:
        raise MissingRealized(
            f"{where}: no {REALIZED_FIELD!r} in payload (keys: "
            f"{sorted(payload) or 'none'}). Nothing in this tree writes it yet "
            "(see the module docstring). Treating it as a zero advance would "
            "score every pair 0.0, tie every comparison, and make a totally "
            "blind engine indistinguishable from a healthy cold start"
        )
    raw = payload[REALIZED_FIELD]
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        raise EmaError(f"{where}: {REALIZED_FIELD}={raw!r} is not a number")
    try:
        return float(raw)
    except ValueError as exc:
        raise EmaError(f"{where}: {REALIZED_FIELD}={raw!r} is not a number") from exc


def _one_close(
    row: Mapping[str, Any], grid: Callable[[dt.date], bool]
) -> RealizedClose:
    """One log row as a `RealizedClose`, or a refusal naming the reason."""
    event_type = str(row.get("event_type", ""))
    where = f"event {row.get('event_id', '?')} ({event_type or 'no type'})"
    if event_type not in CLASSIFIED_EVENT_TYPES:
        raise EmaError(
            f"{where}: this fold has no realization rule for that type. A fold "
            "that ignored an unknown type would silently ignore exactly the "
            "event a decision is owed on"
        )
    if event_type in NON_REALIZING_EVENT_TYPES:
        raise UnrealizedLeak(
            f"{where}: {event_type!r} books no realization — a position it "
            "touches is OPEN or unmoved, and its P&L is a mark. §6.6 ranks "
            "'completed strategy decisions': it entered, managed, and exited"
        )
    symbol = row.get("symbol") or (row.get("payload") or {}).get("symbol")
    strategy_id = str(row.get("strategy_id") or "")
    if not symbol or not strategy_id or strategy_id == NO_TRADE:
        raise EmaError(
            f"{where}: strategy_id={strategy_id!r} symbol={symbol!r} — §6.6's "
            "row is keyed on the PAIR, and a realization that cannot be "
            "attributed to one cannot be scored"
        )
    day = trading_day(row.get("occurred_at"))
    if not grid(day):
        raise EmaError(
            f"{where}: realized on {day} ({day.strftime('%A')}), which the day "
            "grid excludes. Either the grid is wrong for this venue or the "
            "record is wrong about when the trade closed; both are findings and "
            "neither is a row to fold silently"
        )
    payload = row.get("payload") or {}
    return RealizedClose(
        strategy_id=strategy_id,
        symbol=str(symbol),
        day=day,
        realized=_realized_amount(payload, where),
        event_type=event_type,
        trade_id=str(row.get("trade_id") or NO_TRADE),
    )


def realized_closes(
    rows: Iterable[Mapping[str, Any]],
    *,
    grid: Callable[[dt.date], bool] = is_trading_day,
) -> tuple[RealizedClose, ...]:
    """Every REALIZING row, as attributed closes. Non-realizing rows are SKIPPED.

    Skipping is safe HERE and only here: this is the whole-log entry point, so a
    `filled` or a `signal` row is expected and is not a defect. The refusal
    lives one level down in `_one_close`, which any caller handing this engine a
    row it believes realizes something goes through. The two behaviours are
    different questions — *"what in this log is a realization?"* and *"is this
    row one?"* — and collapsing them would make the second unaskable.
    """
    out: list[RealizedClose] = []
    for row in rows:
        if str(row.get("event_type", "")) in REALIZING_EVENT_TYPES:
            out.append(_one_close(row, grid))
    return tuple(out)


def daily_advances(
    closes: Iterable[RealizedClose],
) -> dict[PairKey, dict[dt.date, float]]:
    """§6.6's per-day reduction: **one realized number per pair per day**.

    The reduction is a SUM over the day's closes, which is what makes activity
    stop being an axis: forty $10 wins and two $200 wins produce the same
    advance, and the pair that made $1,000 that day outranks the pair that made
    $400 however many times each of them traded.
    """
    out: dict[PairKey, dict[dt.date, float]] = {}
    for close in closes:
        day_map = out.setdefault(close.key, {})
        day_map[close.day] = day_map.get(close.day, 0.0) + close.realized
    return out


def close_counts(closes: Iterable[RealizedClose]) -> dict[PairKey, int]:
    """Closes per pair. Reported, never ranked on — that is the activity axis."""
    counts: dict[PairKey, int] = {}
    for close in closes:
        counts[close.key] = counts.get(close.key, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# The smoothing itself
# ---------------------------------------------------------------------------


def alpha_for(span: int) -> float:
    """The EMA weight for a span of `span` days: `2 / (span + 1)`.

    The standard span-to-alpha identity, so `SCORE_EMA_SPAN_DAYS` means the same
    thing here as it does anywhere else the operator has calibrated a span.
    Larger span ⇒ smaller alpha ⇒ older days fade more slowly, which is §6.6's
    *"recent days weighted more, older days fade continuously"* with no cliff.
    """
    if span <= 0:
        raise EmaError(
            f"span={span} is not a smoothing window. §12A:801's boot validation "
            "rejects it, and a non-positive span would make alpha undefined or "
            "negative — the ranking would invert"
        )
    return 2.0 / (span + 1.0)


def _grid_days(
    first: dt.date, through: dt.date, grid: Callable[[dt.date], bool]
) -> list[dt.date]:
    """Every grid day in `(first, through]`, in order. Bounded by MAX_GRID_DAYS."""
    days: list[dt.date] = []
    cursor = first
    while cursor < through:
        cursor += _ONE_DAY
        if len(days) >= MAX_GRID_DAYS:
            raise EmaError(
                f"the day grid from {first} to {through} exceeds "
                f"{MAX_GRID_DAYS} days — that is a mis-stamped occurred_at, not "
                "a trading history"
            )
        if grid(cursor):
            days.append(cursor)
    return days


def ema_over_days(
    advances: Mapping[dt.date, float],
    span: int,
    through: dt.date,
    *,
    grid: Callable[[dt.date], bool] = is_trading_day,
) -> PairScore:
    """One pair's realized-P&L EMA, as of `through`. See the module docstring.

    Seeded with the FIRST observed day's advance rather than with a zero: a zero
    seed would put a day the pair did not exist into its history and halve a
    genuine first-day result. Days between the first and `through` that carry no
    close fold a ZERO — that is the decay §6.6 requires, and it is why a pair
    that stopped trading stops steering capital.
    """
    if not advances:
        raise EmaError(
            "no realized advances for this pair — an EMA over an empty history "
            "is not a low score, it is an ABSENT one, and §6.6 makes an absent "
            "score FCFS rather than a rank"
        )
    weight = alpha_for(span)
    observed = sorted(advances)
    first, last = observed[0], observed[-1]
    if through < last:
        raise EmaError(
            f"as-of day {through} is before the last realized close {last}; the "
            "EMA would be computed over a history that has not happened yet"
        )
    value = advances[first]
    for day in _grid_days(first, through, grid):
        value += weight * (advances.get(day, 0.0) - value)
    return PairScore(
        realized_ema=value,
        days_observed=len(observed),
        closes_observed=0,
        first_day=first,
        last_day=last,
        through=through,
        span_days=span,
    )


def score_pairs(
    closes: Sequence[RealizedClose],
    span: int,
    through: dt.date,
    *,
    grid: Callable[[dt.date], bool] = is_trading_day,
) -> dict[PairKey, PairScore]:
    """Every pair's `PairScore`, from a flat sequence of realized closes."""
    counts = close_counts(closes)
    out: dict[PairKey, PairScore] = {}
    for key, advances in daily_advances(closes).items():
        score = ema_over_days(advances, span, through, grid=grid)
        out[key] = dataclasses.replace(score, closes_observed=counts.get(key, 0))
    return out


# ---------------------------------------------------------------------------
# The engine — the span comes from config, at construction, once
# ---------------------------------------------------------------------------


def span_days_from_config(root: Path | None = None) -> int:
    """§12A:836's `SCORE_EMA_SPAN_DAYS`, read through the validating loader.

    There is no default and no fallback. `load_risk_configs` raises on a missing
    file, a missing key or a value its boot rules reject, and a scorer that
    substituted a default for a config it could not read would smooth on a
    number no operator chose.
    """
    from risk_config import load_risk_configs  # pylint: disable=import-outside-toplevel

    raw = load_risk_configs(root).value(SPAN_MODULE, SPAN_KEY)
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise EmaError(f"{SPAN_MODULE}.{SPAN_KEY}={raw!r} is not a number")
    return int(raw)


@dataclasses.dataclass(frozen=True, slots=True)
class RealizedEmaEngine:
    """§6.6's scorer. FROZEN, and its span is fixed at construction (§12.11).

    Frozen rather than merely private: §12.11 is *"boot-loaded, restart-only —
    no hot-reload, a mid-session change would let two decisions inside one open
    trade read different tunables."* A frozen instance attribute makes that
    physical. There is no `reload`, no path is watched, no mtime is read, and
    the only way to observe a changed `risks/scoring.config.json` is to be a new
    process.
    """

    span: int
    grid: Callable[[dt.date], bool] = is_trading_day

    @classmethod
    def from_config(cls, root: Path | None = None) -> RealizedEmaEngine:
        """Build with the span `risks/scoring.config.json` declares. Boot only."""
        return cls(span=span_days_from_config(root))

    def score(
        self, closes: Sequence[RealizedClose], through: dt.date
    ) -> dict[PairKey, PairScore]:
        """Every pair's score as of `through`, under THIS engine's span."""
        return score_pairs(closes, self.span, through, grid=self.grid)

    def snapshot(
        self, closes: Sequence[RealizedClose], through: dt.date
    ) -> RankingSnapshot:
        """The seam's `RankingSnapshot` — ranked rows, ready for `publish`.

        `rank_rows` is the seam's own ordering function and is called HERE, in
        the Scoring process, before publish — which is the one place §6.6
        permits it. A consumer calling it would be a reader computing the
        ranking, and `check_scoring_seam` bans it on the read path by name.
        """
        return self._snapshot_of(self.score(closes, through))

    def snapshot_from_log(
        self, rows: Iterable[Mapping[str, Any]], through: dt.date
    ) -> RankingSnapshot:
        """Plane-1 log rows straight to a publishable snapshot. THE TOP VERB.

        The whole path in one call — extract the realizations, reduce them per
        day, smooth, rank — because that is what the Scoring process actually
        needs and splitting it across three calls at every call site would put
        the same three-step sequence in every caller, where one of them would
        eventually omit a step.

        It also keeps `realized_closes` on a SHIPPED call path rather than a
        gate-only one, which is not bookkeeping: `check_uncalled_entry_points`
        reddened on exactly that (`scripts/nixscore/ema.py::realized_closes`,
        new uncalled surface) and the honest repair was the missing verb, not an
        admission that the extractor has no caller.
        """
        return self.snapshot(realized_closes(rows, grid=self.grid), through)

    def _snapshot_of(self, scored: Mapping[PairKey, PairScore]) -> RankingSnapshot:
        """Scored pairs as the seam's ranked, publishable table."""
        rows: dict[PairKey, RankRow] = rank_rows(
            {key: value.realized_ema for key, value in scored.items()},
            {key: value.days_observed for key, value in scored.items()},
        )
        return RankingSnapshot(rows=rows, span_days=self.span)
