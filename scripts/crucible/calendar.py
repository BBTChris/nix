"""Crucible calendar RUNTIME query module.

Zero network dependency, zero calendar-library dependency. Reads the vendored,
pre-generated artifact under `calendar_data/` (produced by `calendar_gen.py`
at build time) and answers CME session questions for the full CME product
complex, 2008-2030. See ARC CRUCIBLE-CALENDAR-INFRA Success #1 and #5: this
module must never import a calendar library and must do no timezone math --
every boundary in the artifact is already a resolved UTC instant.

Consumers (future arcs): corpus builder, fill model, bar aggregation.

ARC 033 / 0.4 EXTENDED this module rather than adding a second one (doctrine
C.9): §6 of the frozen risk spec needs PER-SYMBOL keying, the closed windows
between sessions, and §7.5's roll schedule, and all three are answered from
the same vendored `calendar_data/` directory by the same zero-dependency
query surface. A parallel `symbol_calendar.py` would have been a second
instrument over one subject, and the two would have drifted at the first
regeneration. The added artifacts (`nix_symbol_map.csv`,
`nix_break_windows.csv`, `nix_roll_schedule.csv`) are produced by
`calendar_ext_gen.py` — see that module for why the GENERATOR is split even
though the query module is not.

**§12.3, and it is the rule this module is measured against.** Every instant
returned from here is UTC. The sessions artifact also stores `eth_open_ct` /
`eth_close_ct`, which are DST-correct audit columns that NOTHING reads —
`Session` does not carry them and no function below names them.
`checks/check_calendar_schema.py` proves that on the shipped bytes: reading a
stored local-time field on a decision path is the failure it exists to catch.
"""

from __future__ import annotations

import csv
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import UTC, date, datetime
from functools import lru_cache
from pathlib import Path

_DATA_DIR = Path(__file__).parent / "calendar_data"
_SESSIONS_FILE = _DATA_DIR / "cme_calendar_sessions.csv"
_SYMBOL_MAP_FILE = _DATA_DIR / "nix_symbol_map.csv"
_BREAK_WINDOWS_FILE = _DATA_DIR / "nix_break_windows.csv"
_ROLL_SCHEDULE_FILE = _DATA_DIR / "nix_roll_schedule.csv"


class UnknownProductGroupError(ValueError):
    """Raised for a product_group not present in the vendored artifact."""


class UnknownSymbolError(ValueError):
    """Raised for a logical symbol not present in the vendored symbol map.

    Distinct from `UnknownProductGroupError` on purpose: a caller asking about
    a symbol that was never provisioned is a configuration defect, while a
    caller asking about an unlisted product group is a data defect, and
    §6.4's fail-closed direction wants them told apart in the log.
    """


@dataclass(frozen=True)
class Session:
    """One trading session for one product group, all instants UTC."""

    date: str  # YYYY-MM-DD, the CT trade date this session is keyed by
    eth_open: datetime
    eth_close: datetime
    rth_open: datetime
    rth_close: datetime
    is_early_close: bool


def _parse_utc(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def _as_date_str(d: date | str) -> str:
    if isinstance(d, str):
        return d
    return d.isoformat()


@lru_cache(maxsize=1)
def _load() -> dict[str, list[Session]]:
    """Load and index the vendored artifact. Cached: the artifact is static
    for the process lifetime (boot-loaded, restart-only lifecycle per
    CLAUDE.md's per-module config convention)."""
    by_group: dict[str, list[Session]] = {}
    if not _SESSIONS_FILE.is_file():
        raise FileNotFoundError(
            f"vendored calendar artifact missing: {_SESSIONS_FILE} "
            "(run scripts/crucible/calendar_gen.py to regenerate)"
        )
    with _SESSIONS_FILE.open(newline="") as f:
        for row in csv.DictReader(f):
            sessions = by_group.setdefault(row["product_group"], [])
            sessions.append(
                Session(
                    date=row["date"],
                    eth_open=_parse_utc(row["eth_open_utc"]),
                    eth_close=_parse_utc(row["eth_close_utc"]),
                    rth_open=_parse_utc(row["rth_open_utc"]),
                    rth_close=_parse_utc(row["rth_close_utc"]),
                    is_early_close=row["is_early_close"] == "1",
                )
            )
    # cme_calendar_sessions.csv is written pre-sorted by (product_group, date)
    # (calendar_gen.py) but the index is rebuilt here rather than trusted
    # blindly -- an out-of-order artifact would silently break every bisect
    # lookup below with no error, so the invariant is asserted once at load.
    for group, sessions in by_group.items():
        dates = [s.date for s in sessions]
        if dates != sorted(dates):
            raise ValueError(f"calendar artifact not sorted for group {group!r}")
    return by_group


def _group_sessions(product_group: str) -> list[Session]:
    by_group = _load()
    sessions = by_group.get(product_group)
    if sessions is None:
        raise UnknownProductGroupError(
            f"unknown product_group {product_group!r}; known: {sorted(by_group)}"
        )
    return sessions


def _find_session(product_group: str, on_date: date | str) -> Session | None:
    sessions = _group_sessions(product_group)
    target = _as_date_str(on_date)
    dates = [s.date for s in sessions]
    idx = bisect_right(dates, target) - 1
    if 0 <= idx < len(sessions) and dates[idx] == target:
        return sessions[idx]
    return None


def session_bounds(
    product_group: str, on_date: date | str
) -> tuple[datetime, datetime, datetime, datetime] | None:
    """(rth_open, rth_close, eth_open, eth_close), all UTC. None if `on_date`
    is not a trading session for `product_group` (holiday)."""
    session = _find_session(product_group, on_date)
    if session is None:
        return None
    return (session.rth_open, session.rth_close, session.eth_open, session.eth_close)


def is_early_close(product_group: str, on_date: date | str) -> bool | datetime:
    """False if not a session or a normal session; True is never returned
    without an override -- the actual early close instant (UTC) is returned
    directly when the day is an early close, so a caller never has to
    re-derive it from session_bounds."""
    session = _find_session(product_group, on_date)
    if session is None or not session.is_early_close:
        return False
    return session.eth_close


def is_session_open(product_group: str, utc_instant: datetime) -> bool:
    """Whether `product_group` is inside a live ETH session at `utc_instant`."""
    if utc_instant.tzinfo is None:
        raise ValueError("utc_instant must be timezone-aware")
    sessions = _group_sessions(product_group)
    opens = [s.eth_open for s in sessions]
    idx = bisect_right(opens, utc_instant) - 1
    if idx < 0:
        return False
    session = sessions[idx]
    return session.eth_open <= utc_instant < session.eth_close


def next_close(product_group: str, utc_instant: datetime) -> datetime:
    """UTC instant of the next ETH close at or after `utc_instant` -- the
    close of the live session if one is open, else the close of the next
    session to open."""
    if utc_instant.tzinfo is None:
        raise ValueError("utc_instant must be timezone-aware")
    sessions = _group_sessions(product_group)
    closes = [s.eth_close for s in sessions]
    idx = bisect_left(closes, utc_instant)
    if idx >= len(closes):
        # utc_instant is after the last close in the vendored span -- a
        # genuine "no more data" condition, never guessed at silently.
        raise ValueError(
            f"no session close at or after {utc_instant.isoformat()} for "
            f"{product_group!r} -- outside vendored artifact span"
        )
    return closes[idx]


def trading_days(product_group: str, start: date | str, end: date | str) -> list[date]:
    """Sorted, gap-free (per the vendored artifact) list of session dates for
    `product_group` in [start, end] inclusive."""
    start_str, end_str = _as_date_str(start), _as_date_str(end)
    if start_str > end_str:
        raise ValueError(f"start {start_str} is after end {end_str}")
    sessions = _group_sessions(product_group)
    dates = [s.date for s in sessions]
    lo = bisect_left(dates, start_str)
    hi = bisect_right(dates, end_str)
    return [date.fromisoformat(d) for d in dates[lo:hi]]


def known_product_groups() -> tuple[str, ...]:
    """The locked six product groups the vendored artifact carries, sorted."""
    return tuple(sorted(_load()))


def artifact_span(product_group: str) -> tuple[str, str]:
    """(first_session_date, last_session_date) for `product_group`."""
    sessions = _group_sessions(product_group)
    return sessions[0].date, sessions[-1].date


# ---------------------------------------------------------------------------
# ARC 033 / 0.4 — per-symbol keying, closed windows, roll schedule
#
# Everything below answers from `nix_*.csv` under the same `calendar_data/`
# directory, with the same rules as everything above: stdlib only, no
# timezone math, every returned instant already a resolved UTC instant.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BreakWindow:
    """The closed window between one session's close and the next session's
    open, for one product group. Half-open `[start, end)`.

    `klass` is DERIVED (see `calendar_ext_gen._classify_break`), never
    asserted: DAILY_BREAK / WEEKEND / HOLIDAY_BREAK. For the four intraday
    groups DAILY_BREAK is the CME daily maintenance halt; for agriculturals it
    is the whole overnight closed period, which is why the column is not named
    "maintenance" — see the generator.
    """

    product_group: str
    date: str
    start: datetime
    end: datetime
    klass: str


@dataclass(frozen=True)
class Roll:
    """§7.5's front-month identity for one symbol over one interval.

    `front_from` and `roll_at` are both resolved UTC session-close instants and
    the interval is half-open `[front_from, roll_at)`. Consecutive rows for a
    symbol are contiguous by construction — each row's `front_from` IS the
    previous row's `roll_at` — so there is no instant inside the schedule's
    span with two front months and none with zero.

    PROVISIONAL: every row is rule-derived and stamped `high_risk=1`. §7.5
    sources the live schedule from the calendar poller (front month = volume
    leader), which no offline artifact can observe.
    """

    symbol: str
    contract: str
    front_from: datetime
    roll_at: datetime
    last_trading_date: str
    high_risk: bool


@lru_cache(maxsize=1)
def _load_symbol_map() -> dict[str, str]:
    """symbol -> product_group. Cached like `_load`, for the same reason."""
    if not _SYMBOL_MAP_FILE.is_file():
        raise FileNotFoundError(
            f"vendored symbol map missing: {_SYMBOL_MAP_FILE} "
            "(run scripts/crucible/calendar_ext_gen.py to regenerate)"
        )
    with _SYMBOL_MAP_FILE.open(newline="") as f:
        return {row["symbol"]: row["product_group"] for row in csv.DictReader(f)}


@lru_cache(maxsize=1)
def _load_breaks() -> dict[str, list[BreakWindow]]:
    if not _BREAK_WINDOWS_FILE.is_file():
        raise FileNotFoundError(
            f"vendored break windows missing: {_BREAK_WINDOWS_FILE} "
            "(run scripts/crucible/calendar_ext_gen.py to regenerate)"
        )
    by_group: dict[str, list[BreakWindow]] = {}
    with _BREAK_WINDOWS_FILE.open(newline="") as f:
        for row in csv.DictReader(f):
            by_group.setdefault(row["product_group"], []).append(
                BreakWindow(
                    product_group=row["product_group"],
                    date=row["date"],
                    start=_parse_utc(row["break_start_utc"]),
                    end=_parse_utc(row["break_end_utc"]),
                    klass=row["break_class"],
                )
            )
    for group, windows in by_group.items():
        if [w.date for w in windows] != sorted(w.date for w in windows):
            raise ValueError(f"break-window artifact not sorted for group {group!r}")
    return by_group


@lru_cache(maxsize=1)
def _load_rolls() -> dict[str, list[Roll]]:
    if not _ROLL_SCHEDULE_FILE.is_file():
        raise FileNotFoundError(
            f"vendored roll schedule missing: {_ROLL_SCHEDULE_FILE} "
            "(run scripts/crucible/calendar_ext_gen.py to regenerate)"
        )
    by_symbol: dict[str, list[Roll]] = {}
    with _ROLL_SCHEDULE_FILE.open(newline="") as f:
        for row in csv.DictReader(f):
            by_symbol.setdefault(row["symbol"], []).append(
                Roll(
                    symbol=row["symbol"],
                    contract=row["contract"],
                    front_from=_parse_utc(row["front_from_utc"]),
                    roll_at=_parse_utc(row["roll_at_utc"]),
                    last_trading_date=row["last_trading_date"],
                    high_risk=row["high_risk"] == "1",
                )
            )
    for symbol, rolls in by_symbol.items():
        starts = [r.front_from for r in rolls]
        if starts != sorted(starts):
            raise ValueError(f"roll schedule not sorted for symbol {symbol!r}")
    return by_symbol


def known_symbols() -> tuple[str, ...]:
    """The logical symbols the vendored symbol map carries, sorted."""
    return tuple(sorted(_load_symbol_map()))


def product_group_of(symbol: str) -> str:
    """The product group whose session calendar governs `symbol` (§6.1)."""
    mapping = _load_symbol_map()
    group = mapping.get(symbol)
    if group is None:
        raise UnknownSymbolError(f"unknown symbol {symbol!r}; known: {sorted(mapping)}")
    return group


def symbol_session_bounds(
    symbol: str, on_date: date | str
) -> tuple[datetime, datetime, datetime, datetime] | None:
    """`session_bounds` keyed by SYMBOL — §6.1's "per-symbol via live calendar".

    A thin re-key, deliberately: two symbols sharing a product group share a
    session calendar by construction, and materialising a per-symbol copy of
    35k rows would create two representations of one fact that can disagree.
    """
    return session_bounds(product_group_of(symbol), on_date)


def break_window(product_group: str, on_date: date | str) -> BreakWindow | None:
    """The closed window that FOLLOWS `on_date`'s session, or None.

    Keyed by the date of the session whose close opens the window, so a caller
    holding a session can ask for the gap after it without arithmetic.
    """
    by_group = _load_breaks()
    windows = by_group.get(product_group)
    if windows is None:
        raise UnknownProductGroupError(
            f"unknown product_group {product_group!r}; known: {sorted(by_group)}"
        )
    target = _as_date_str(on_date)
    dates = [w.date for w in windows]
    idx = bisect_right(dates, target) - 1
    if 0 <= idx < len(windows) and dates[idx] == target:
        return windows[idx]
    return None


def _symbol_rolls(symbol: str) -> list[Roll]:
    by_symbol = _load_rolls()
    rolls = by_symbol.get(symbol)
    if rolls is None:
        raise UnknownSymbolError(
            f"no roll schedule for symbol {symbol!r}; known: {sorted(by_symbol)}"
        )
    return rolls


def front_contract(symbol: str, utc_instant: datetime) -> Roll | None:
    """§7.5's front-month identity at `utc_instant`, or None if off-span.

    None rather than a nearest-neighbour guess: §7.5 makes the roll instant a
    defined boundary for Renko/backfill continuity, and a guessed identity is
    the phantom stitch across contracts it forbids.
    """
    if utc_instant.tzinfo is None:
        raise ValueError("utc_instant must be timezone-aware")
    rolls = _symbol_rolls(symbol)
    starts = [r.front_from for r in rolls]
    idx = bisect_right(starts, utc_instant) - 1
    if idx < 0:
        return None
    roll = rolls[idx]
    return roll if roll.front_from <= utc_instant < roll.roll_at else None


def next_roll(symbol: str, utc_instant: datetime) -> datetime | None:
    """The next roll instant at or after `utc_instant` (UTC), or None."""
    if utc_instant.tzinfo is None:
        raise ValueError("utc_instant must be timezone-aware")
    rolls = _symbol_rolls(symbol)
    ends = [r.roll_at for r in rolls]
    idx = bisect_left(ends, utc_instant)
    return ends[idx] if idx < len(ends) else None
