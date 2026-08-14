"""Crucible calendar RUNTIME query module.

Zero network dependency, zero calendar-library dependency. Reads the vendored,
pre-generated artifact under `calendar_data/` (produced by `calendar_gen.py`
at build time) and answers CME session questions for the full CME product
complex, 2008-2030. See ARC CRUCIBLE-CALENDAR-INFRA Success #1 and #5: this
module must never import a calendar library and must do no timezone math --
every boundary in the artifact is already a resolved UTC instant.

Consumers (future arcs): corpus builder, fill model, bar aggregation.
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


class UnknownProductGroupError(ValueError):
    """Raised for a product_group not present in the vendored artifact."""


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
