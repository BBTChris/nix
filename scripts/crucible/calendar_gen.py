"""Crucible calendar GENERATOR — build-time only.

Produces the vendored, deterministic CME session-calendar artifact consumed by
`scripts/crucible/calendar.py` at runtime. This module is the ONLY place in the
Crucible calendar subsystem allowed to import a calendar library. It makes no
network call itself (all external corroboration below is static data recorded
at authoring time via WebSearch, not a live call at generation time) but its
dependency (`pandas_market_calendars`) is a BUILD/dev dependency only — never
installed in the runtime venv. See ARC CRUCIBLE-CALENDAR-INFRA, Success #1/#9.

Run: .venv/bin/python -m scripts.crucible.calendar_gen
Output: scripts/crucible/calendar_data/{cme_calendar_sessions.csv,
        cme_calendar_reconciliation.csv, cme_calendar_provenance.json}
"""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import UTC, date, datetime, time
from importlib.metadata import version as pkg_version
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

import pandas as pd  # pylint: disable=import-error
import pandas_market_calendars as mcal  # pylint: disable=import-error

SPAN_START = "2008-01-01"
SPAN_END = "2030-12-31"
CT = ZoneInfo("America/Chicago")

DATA_DIR = Path(__file__).parent / "calendar_data"
SESSIONS_FILE = DATA_DIR / "cme_calendar_sessions.csv"
RECONCILIATION_FILE = DATA_DIR / "cme_calendar_reconciliation.csv"
PROVENANCE_FILE = DATA_DIR / "cme_calendar_provenance.json"

# product_group -> pandas_market_calendars calendar name. Locked six groups
# (arc FACTS CC CANNOT DERIVE). Chosen over exchange_calendars because this
# library ships product-group-scoped CME calendars directly; exchange_calendars
# does not split CME futures by product group.
GROUP_CALENDARS = {
    "agriculturals": "CME_Agriculture",
    "energy": "CMEGlobex_Energy",
    "equity_index": "CME_Equity",
    "fx": "CME_FX",
    "interest_rates": "CME_InterestRate",
    "metals": "CMEGlobex_Metals",
}

# RTH (regular-trading-hours / settlement-window) wall-clock, America/Chicago.
# SOURCE: WebSearch corroboration performed during ARC CRUCIBLE-CALENDAR-INFRA
# (2026-08-14), cross-checked against multiple independent secondary sources
# and against this generator's own library's `regular_market_times` regime
# dates. Direct cmegroup.com contractSpecs fetch timed out twice (recorded,
# not silently skipped) — this is NOT a primary-source citation, it is the
# documented best-effort per the arc's hard limit on settlement-time guesses.
# FX has no distinct RTH: modern FX futures trade one continuous session with
# no concentrated "pit hours" window, so rth == eth for fx (value: None).
RTH_HOURS_CT: dict[str, tuple[time, time] | None] = {
    "equity_index": (time(8, 30), time(15, 15)),  # ES-representative
    "energy": (time(8, 0), time(13, 30)),  # CL-representative
    "metals": (time(7, 20), time(12, 30)),  # GC-representative
    "interest_rates": (time(7, 20), time(14, 0)),  # ZN-representative
    "agriculturals": (time(8, 30), time(13, 20)),  # grain-complex-representative
    "fx": None,
}

# Rows for which primary-source CME corroboration was actually obtained this
# session (cmegroup.com/media-room press release, via WebSearch — NOT the
# library). Used to upgrade specific HIGH-RISK pre-2010 non-equity rows from
# LIBRARY to CME-VERIFIED. Deliberately small and explicit: only rows with a
# real citation are upgraded — nothing is upgraded by inference or pattern-
# matching (Success #7 / hard-limit: never silently trust pre-2010 non-equity).
CME_VERIFIED_OVERRIDES: dict[tuple[str, str], str] = {
    ("energy", "2008-01-01"): (
        "NYMEX 2008 holiday schedule (cmegroup.com/media-room press release, "
        "2007-11-20): closed New Year's Day, elec. trading reopens 2008-01-01 18:00 UTC"
    ),
    ("metals", "2008-01-01"): (
        "NYMEX 2008 holiday schedule (cmegroup.com/media-room press release, "
        "2007-11-20): COMEX co-located with NYMEX holiday calendar, closed New Year's Day"
    ),
    ("energy", "2008-03-21"): (
        "NYMEX 2008 holiday schedule (cmegroup.com/media-room press release, "
        "2007-11-20): closed Good Friday, elec. trading reopens 2008-03-23 18:00 UTC"
    ),
    ("metals", "2008-03-21"): (
        "NYMEX 2008 holiday schedule (cmegroup.com/media-room press release, "
        "2007-11-20): COMEX co-located with NYMEX holiday calendar, closed Good Friday"
    ),
}

SESSION_FIELDS = [
    "product_group",
    "date",
    "eth_open_utc",
    "eth_close_utc",
    "rth_open_utc",
    "rth_close_utc",
    "is_early_close",
    "eth_open_ct",
    "eth_close_ct",
]
RECONCILIATION_FIELDS = [
    "product_group",
    "date",
    "event_type",
    "source",
    "high_risk",
    "notes",
]


def _fmt_utc(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fmt_ct(dt: datetime) -> str:
    return dt.astimezone(CT).strftime("%Y-%m-%dT%H:%M:%S%z")


def _rth_bounds(group: str, session_date, eth_open: datetime, eth_close: datetime):
    spec = RTH_HOURS_CT[group]
    if spec is None:
        return eth_open, eth_close
    open_t, close_t = spec
    rth_open = datetime.combine(session_date, open_t, tzinfo=CT).astimezone(UTC)
    rth_close = datetime.combine(session_date, close_t, tzinfo=CT).astimezone(UTC)
    # An early-close day truncates the WHOLE session, RTH included -- the
    # static per-group time-of-day cannot outlive the session's actual
    # (possibly early) close. Without this cap, an early-close session
    # produces eth_close < rth_close, an inverted window no caller expects.
    # Order is enforced structurally: rth_open <= rth_close <= eth_close.
    rth_close = min(rth_close, eth_close)
    rth_open = min(rth_open, rth_close)
    return rth_open, rth_close


def _classify(group: str, date_str: str) -> tuple[str, bool, str]:
    year = int(date_str[:4])
    high_risk = group != "equity_index" and year < 2010
    override = CME_VERIFIED_OVERRIDES.get((group, date_str))
    if override is not None:
        return "CME-VERIFIED", False, override
    return "LIBRARY", high_risk, ""


def _session_row(group: str, date_str: str, is_ec: bool, eth_open, eth_close) -> dict:
    rth_open, rth_close = _rth_bounds(
        group, date.fromisoformat(date_str), eth_open, eth_close
    )
    return {
        "product_group": group,
        "date": date_str,
        "eth_open_utc": _fmt_utc(eth_open),
        "eth_close_utc": _fmt_utc(eth_close),
        "rth_open_utc": _fmt_utc(rth_open),
        "rth_close_utc": _fmt_utc(rth_close),
        "is_early_close": "1" if is_ec else "0",
        "eth_open_ct": _fmt_ct(eth_open),
        "eth_close_ct": _fmt_ct(eth_close),
    }


def _reconciliation_row(group: str, date_str: str, event_type: str) -> dict:
    source, high_risk, notes = _classify(group, date_str)
    return {
        "product_group": group,
        "date": date_str,
        "event_type": event_type,
        "source": source,
        "high_risk": "1" if high_risk else "0",
        "notes": notes,
    }


def _session_and_early_close_rows(
    group: str, cal, schedule
) -> tuple[list[dict], list[dict]]:
    early_dates = set(cal.early_closes(schedule).index)
    session_rows: list[dict] = []
    reconciliation_rows: list[dict] = []
    for ts_raw, row in schedule.iterrows():
        # DataFrame.iterrows() is stubbed to yield a bare `Hashable` index;
        # at runtime it is always the DatetimeIndex's own pd.Timestamp
        # element (verified directly) -- narrowed once here rather than
        # sprinkling casts at every use below.
        ts = cast(pd.Timestamp, ts_raw)
        date_str = ts.strftime("%Y-%m-%d")
        is_ec = ts in early_dates
        session_rows.append(
            _session_row(
                group,
                date_str,
                is_ec,
                row["market_open"].to_pydatetime(),
                row["market_close"].to_pydatetime(),
            )
        )
        if is_ec:
            reconciliation_rows.append(
                _reconciliation_row(group, date_str, "EARLY_CLOSE")
            )
    return session_rows, reconciliation_rows


def _holiday_dates_in_span(cal) -> list[str]:
    # pandas_market_calendars' own runtime type for holidays() is
    # CustomBusinessDay, whose `.holidays` attribute exists at runtime
    # (verified directly) but is absent from its type stub -- a stub
    # gap in the third-party library, not a defect here.
    holiday_calendar: Any = cal.holidays()
    return [
        d for d in holiday_calendar.holidays if SPAN_START <= str(d)[:10] <= SPAN_END
    ]


def _generate_group(group: str, cal_name: str) -> tuple[list[dict], list[dict]]:
    """Session rows + reconciliation rows for one product group."""
    cal = mcal.get_calendar(cal_name)
    schedule = cal.schedule(start_date=SPAN_START, end_date=SPAN_END)
    session_rows, reconciliation_rows = _session_and_early_close_rows(
        group, cal, schedule
    )
    for h in _holiday_dates_in_span(cal):
        reconciliation_rows.append(_reconciliation_row(group, str(h)[:10], "HOLIDAY"))
    return session_rows, reconciliation_rows


def generate() -> dict:
    """Build the full session + reconciliation row sets, all six groups."""
    session_rows: list[dict] = []
    reconciliation_rows: list[dict] = []

    for group, cal_name in GROUP_CALENDARS.items():
        group_sessions, group_reconciliation = _generate_group(group, cal_name)
        session_rows.extend(group_sessions)
        reconciliation_rows.extend(group_reconciliation)

    # Reconciliation gate (Success #7): every row must resolve to a source.
    # This can never be false given _classify's total fallback to LIBRARY,
    # which is exactly the point -- the invariant is enforced structurally,
    # not hoped for. A future refactor that introduces an unclassified path
    # raises here rather than silently emitting an UNRECONCILED row. `raise`,
    # not `assert`: an assert is stripped under `python -O`, which would
    # silently disarm the one gate Success #7 requires stay armed.
    for r in reconciliation_rows:
        if r["source"] not in ("LIBRARY", "CME-VERIFIED", "MANUAL"):
            raise ValueError(f"UNRECONCILED row, refusing to emit: {r}")

    session_rows.sort(key=lambda r: (r["product_group"], r["date"]))
    reconciliation_rows.sort(
        key=lambda r: (r["product_group"], r["date"], r["event_type"])
    )
    return {"sessions": session_rows, "reconciliation": reconciliation_rows}


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _content_hash(sessions_bytes: bytes, reconciliation_bytes: bytes) -> str:
    h = hashlib.sha256()
    h.update(sessions_bytes)
    h.update(reconciliation_bytes)
    return h.hexdigest()


def main() -> None:
    """Generate, write, and print a summary of the vendored artifact."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data = generate()

    _write_csv(SESSIONS_FILE, SESSION_FIELDS, data["sessions"])
    _write_csv(RECONCILIATION_FILE, RECONCILIATION_FIELDS, data["reconciliation"])

    content_hash = _content_hash(
        SESSIONS_FILE.read_bytes(), RECONCILIATION_FILE.read_bytes()
    )

    source_counts: dict[str, int] = {}
    high_risk_count = 0
    for r in data["reconciliation"]:
        source_counts[r["source"]] = source_counts.get(r["source"], 0) + 1
        if r["high_risk"] == "1":
            high_risk_count += 1

    provenance = {
        "content_hash_sha256": content_hash,
        "content_hash_excludes": ["generated_utc"],
        "generator_library": "pandas_market_calendars",
        "generator_library_version": pkg_version("pandas_market_calendars"),
        "generated_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "span": {"start": SPAN_START, "end": SPAN_END},
        "product_groups": sorted(GROUP_CALENDARS),
        "cme_source_reference": (
            "CME Group official holiday/hours pages (cmegroup.com/trading-hours.html, "
            "cmegroup.com/media-room); reconciliation performed via WebSearch "
            "corroboration 2026-08-14 (direct contractSpecs fetch timed out) "
            "-- see cme_calendar_reconciliation.csv for per-row source labels"
        ),
        "reconciliation_summary": source_counts,
        "high_risk_row_count": high_risk_count,
        "row_counts": {
            "sessions": len(data["sessions"]),
            "reconciliation": len(data["reconciliation"]),
        },
    }
    PROVENANCE_FILE.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n")

    print(f"wrote {SESSIONS_FILE} ({len(data['sessions'])} rows)")
    print(f"wrote {RECONCILIATION_FILE} ({len(data['reconciliation'])} rows)")
    print(f"wrote {PROVENANCE_FILE}")
    print(f"content_hash_sha256={content_hash}")


if __name__ == "__main__":
    main()
