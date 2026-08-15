"""Calendar EXTENSION generator — build-time only, runtime venv, no library.

ARC 033 / Phase 0.4. Produces the three vendored artifacts §6 of the frozen
risk spec needs and the pre-existing CME session artifact does not carry:

  1. `nix_symbol_map.csv`      — logical symbol → CME product group (§6.1's
                                 "per-symbol via live calendar"; the existing
                                 artifact is keyed by product GROUP only)
  2. `nix_break_windows.csv`   — the closed window between one session's close
                                 and the next session's open, classified
                                 (§6.4's window set; §6.5's "a window, not code")
  3. `nix_roll_schedule.csv`   — §7.5's front-month identity and roll instant

plus `nix_calendar_ext_provenance.json`, which hash-stamps all three AND
CHAINS to the upstream artifact's own stamp.

---

## WHY THIS IS A SECOND GENERATOR AND NOT AN EDIT TO `calendar_gen.py` (C.9)

Doctrine C.9 forbids a duplicate instrument, so the split has to be argued,
not assumed. These two generators differ in every dimension that matters:

* **Input.** `calendar_gen.py` reads a calendar LIBRARY
  (`pandas_market_calendars`) plus authoring-time web corroboration. This
  module reads **only the bytes `calendar_gen.py` already vendored**. It is a
  pure function of committed data.
* **Venv.** `calendar_gen.py` refuses to run outside `.venv-dev` (its own
  wrong-venv guard, D3.111) because its dependency must never land in the
  shared runtime venv. This module has no third-party dependency at all and
  runs under the shared `.venv`. Folding it into `calendar_gen.py` would make
  regenerating a symbol map require a dev venv that is not provisioned on
  every worktree — measured: `.venv-dev` does not exist in this one.
* **Blast radius.** `calendar_gen.py` rewrites 35k rows whose provenance
  argument depends on byte-stability; this module never touches them. Keeping
  the two apart is what lets the extension be regenerated without putting the
  upstream artifact's hash at risk.

They are not two instruments measuring one subject; they are two stages of one
pipeline, and the chained hash below is the join.

Run: .venv/bin/python -m crucible.calendar_ext_gen   (from `scripts/`)
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from itertools import pairwise
from pathlib import Path

DATA_DIR = Path(__file__).parent / "calendar_data"
UPSTREAM_SESSIONS = DATA_DIR / "cme_calendar_sessions.csv"
UPSTREAM_RECONCILIATION = DATA_DIR / "cme_calendar_reconciliation.csv"
UPSTREAM_PROVENANCE = DATA_DIR / "cme_calendar_provenance.json"

SYMBOL_MAP_FILE = DATA_DIR / "nix_symbol_map.csv"
BREAK_WINDOWS_FILE = DATA_DIR / "nix_break_windows.csv"
ROLL_SCHEDULE_FILE = DATA_DIR / "nix_roll_schedule.csv"
EXT_PROVENANCE_FILE = DATA_DIR / "nix_calendar_ext_provenance.json"

#: The vendored artifact's span, restated NOWHERE — read from its provenance.
#: (directive 3.)

# ---------------------------------------------------------------------------
# 1. Symbol map
# ---------------------------------------------------------------------------

#: Logical symbol → the product group whose session calendar governs it.
#:
#: **The SYMBOL SET is not minted here.** §7:498 locks five logical symbols and
#: `scripts/nixalloc/seam.py:BUCKET_OF` is their in-tree home; this module is
#: checked against that set by `check_calendar_schema` rather than declaring a
#: sixth opinion about it. What IS new here is the second column: a
#: correlation BUCKET (§7, a risk concept — equities/energy/metals/rates) and a
#: CME product GROUP (§6, an exchange-calendar concept —
#: equity_index/energy/metals/interest_rates) are different mappings that
#: happen to agree on these five symbols. Deriving one from the other would
#: bind a calendar fact to a correlation ruling, and the next symbol added
#: (say a second energy contract on a different group calendar) would break
#: the coincidence silently.
#:
#: SOURCE, and it is not invention: `calendar_gen.py`'s own `RTH_HOURS_CT`
#: table annotates four of the six groups with the very symbol it chose that
#: group's RTH window to represent — `equity_index: ES-representative`,
#: `energy: CL-representative`, `metals: GC-representative`,
#: `interest_rates: ZN-representative`. NQ follows from §7:498's own sentence
#: (`equities {ES, NQ}`) plus ES → equity_index. The mapping is therefore the
#: one the shipped generator already committed to, read back out.
SYMBOL_PRODUCT_GROUP: dict[str, tuple[str, str]] = {
    "ES": ("equity_index", "calendar_gen.RTH_HOURS_CT: equity_index ES-representative"),
    "NQ": ("equity_index", "spec §7:498 equities {ES, NQ} + ES->equity_index"),
    "CL": ("energy", "calendar_gen.RTH_HOURS_CT: energy CL-representative"),
    "GC": ("metals", "calendar_gen.RTH_HOURS_CT: metals GC-representative"),
    "ZN": (
        "interest_rates",
        "calendar_gen.RTH_HOURS_CT: interest_rates ZN-representative",
    ),
}

SYMBOL_MAP_FIELDS = ["symbol", "product_group", "source"]

# ---------------------------------------------------------------------------
# 2. Break windows
# ---------------------------------------------------------------------------

BREAK_FIELDS = [
    "product_group",
    "date",
    "break_start_utc",
    "break_end_utc",
    "break_class",
]

#: Break classes. DERIVED per row from the vendored data, never asserted:
#: what separates them is which calendar dates the gap spans and whether the
#: reconciliation artifact records a HOLIDAY on any of them.
#:
#: A note a later reader needs: for the four intraday groups the DAILY_BREAK
#: row IS the CME daily maintenance halt. For `agriculturals` the daily gap is
#: the whole overnight closed period, which is longer than a maintenance halt
#: and is not solely one. This module therefore does NOT name the column
#: "maintenance": that would assert an exchange fact about ag that the
#: vendored data does not contain. The class says what was measured — the
#: exchange is closed between these two instants — and a §6 window only needs
#: that much.
CLASS_DAILY = "DAILY_BREAK"
CLASS_WEEKEND = "WEEKEND"
CLASS_HOLIDAY = "HOLIDAY_BREAK"
CLASS_UNCLASSIFIED = "UNCLASSIFIED"

# ---------------------------------------------------------------------------
# 3. Roll schedule (§7.5)
# ---------------------------------------------------------------------------

ROLL_FIELDS = [
    "symbol",
    "contract",
    "front_from_utc",
    "roll_at_utc",
    "last_trading_date",
    "rule",
    "source",
    "high_risk",
]

#: Month codes, the one piece of this that is a universal convention.
MONTH_CODE = "FGHJKMNQUVXZ"


@dataclass(frozen=True)
class RollRule:
    """One symbol's contract cycle and roll convention, stated as a rule.

    **STATUS: PROVISIONAL, and every emitted row is stamped `high_risk=1`.**
    §7.5 says the roll schedule is *sourced by the calendar poller* — front
    month is the VOLUME LEADER, which is an observation no offline artifact
    can make. What is frozen here is the SCHEMA plus a deterministic
    rule-derived schedule that is right about the cycle and approximately
    right about the instant, so that:
      * downstream code has non-vacuous data to be built and tested against,
      * and the day the poller lands, replacing these rows is a data swap
        that changes no schema and no reader.
    Nothing here may be treated as CME-verified. `source` carries the
    corroboration state per row and `high_risk` is 1 on all of them.
    """

    #: Month codes carrying front-month liquidity, in calendar order.
    months: str
    #: How the last trading day is derived. See `_last_trading_date`.
    ltd_rule: str
    #: Which instant the roll is measured back from: "ltd" (last trading day)
    #: or "fnd" (first notice day = the last business day of the month
    #: preceding the delivery month). Anchoring on the instant a source
    #: actually names beats converting every convention into one currency and
    #: losing which fact came from where.
    roll_anchor: str
    #: Calendar days before `roll_anchor` at which front-month identity moves.
    roll_lead_days: int
    #: Corroboration state for this rule, recorded on every emitted row.
    source: str


#: WHAT THE AUTHORING-TIME RESEARCH ACTUALLY RETURNED, including where it
#: CONTRADICTED the assumption this module was first written against.
#:
#: **Every cmegroup.com page and PDF was UNFETCHABLE** — WebFetch timed out on
#: all of them and a direct request returned *"This IP address is blocked due
#: to suspected web scraping activity"*. Every CME-attributed fact below rests
#: on a search-engine extract of those pages, not on a document that was
#: rendered and read. That is recorded here rather than smoothed over, and it
#: is why `high_risk=1` on every emitted row.
#:
#: **The contradiction, recorded because it changed the data:** this module
#: first carried an equity-index roll of *"the Thursday 8 days before the
#: third Friday"*. Two independent sources report CME's own published
#: customary roll date as **the Monday prior to the third Friday** (4 days);
#: the 8-day figure appears only in third-party trade press describing where
#: volume and open interest are observed to migrate. §7.5's criterion is the
#: VOLUME LEADER, which is the trade press's claim — but the exchange-attributed
#: figure is the better-sourced one, so the data uses 4 and the conflict is
#: carried on every ES/NQ row instead of being resolved by preference.
ROLL_RULES: dict[str, RollRule] = {
    "ES": RollRule(
        months="HMUZ",
        ltd_rule="third_friday",
        roll_anchor="ltd",
        roll_lead_days=4,
        source=(
            "RULE:CME equity-index quarterly cycle H/M/U/Z; LTD = third Friday "
            "of the contract month, cash-settled to the SOQ, no first notice "
            "day. Roll = CME's stated CUSTOMARY roll date, the Monday prior to "
            "the third Friday. CONFLICT ON RECORD: third-party trade press "
            "reports volume/OI actually migrating the Thursday ~8 days before "
            "the third Friday; unresolved because cmegroup.com/trading/"
            "equity-index/rolldates.html could not be fetched (IP-blocked). "
            "Search-extract attribution only, NOT a rendered primary source"
        ),
    ),
    "NQ": RollRule(
        months="HMUZ",
        ltd_rule="third_friday",
        roll_anchor="ltd",
        roll_lead_days=4,
        source=(
            "RULE:same cycle, LTD and roll convention as ES (one CME "
            "equity-index roll calendar). Carries the same unresolved 4-vs-8 "
            "day conflict. Search-extract attribution only, NOT primary source"
        ),
    ),
    "ZN": RollRule(
        months="HMUZ",
        ltd_rule="cbot_note_ltd",
        roll_anchor="fnd",
        roll_lead_days=0,
        source=(
            "RULE:CBOT Treasury quarterly cycle H/M/U/Z; LTD = the 7th business "
            "day preceding the last business day of the delivery month. Roll "
            "anchored on FIRST POSITION DAY (last business day of the month "
            "preceding delivery) per CME's 'Pace of the Roll': the majority of "
            "open interest rolls in the last ~10 business days before the "
            "contract month begins, centred on that day. Search-extract "
            "attribution only, NOT primary source"
        ),
    ),
    "CL": RollRule(
        months="FGHJKMNQUVXZ",
        ltd_rule="nymex_cl_ltd",
        roll_anchor="ltd",
        roll_lead_days=4,
        source=(
            "RULE:NYMEX WTI is listed in ALL TWELVE calendar months; LTD = 3 "
            "business days before the 25th calendar day of the month PRECEDING "
            "the delivery month (and, where the 25th is not a business day, 3 "
            "business days prior to the last business day preceding it). "
            "NOT CORROBORATED: no exchange-published roll date was found for "
            "CL at all; the 4-calendar-day lead is a broker-material "
            "convention and is the weakest figure in this table"
        ),
    ),
    "GC": RollRule(
        months="GJMQZ",
        ltd_rule="comex_gc_ltd",
        roll_anchor="fnd",
        roll_lead_days=5,
        source=(
            "RULE:COMEX gold lists many months; the ACTIVELY traded set used "
            "here is G/J/M/Q/Z (Feb/Apr/Jun/Aug/Dec), CME's own TAS-eligible "
            "active months. DISPUTED: several third-party sources add October "
            "(V) to the active set; unresolved, and a missing active month "
            "shows up as a longer front-month interval, never as a gap. LTD = "
            "the 3rd-last business day of the delivery month; roll anchored on "
            "First Notice Day (last business day of the preceding month) less "
            "5 calendar days. NOT CORROBORATED: broker/blog figures for the "
            "pre-FND migration conflict across 2-10 days"
        ),
    ),
}

#: The authoring-time source list, carried into the provenance stamp so a
#: later reader can re-check the weakest rows without re-doing the search.
ROLL_SOURCE_NOTES = {
    "fetch_status": (
        "every cmegroup.com URL below was UNFETCHABLE at authoring time "
        "(WebFetch timeout; direct request returned 'This IP address is "
        "blocked due to suspected web scraping activity'). CME-attributed "
        "facts rest on search-engine extracts, not rendered documents"
    ),
    "urls": [
        "https://www.cmegroup.com/markets/equities/sp/e-mini-sandp500.contractSpecs.html",
        "https://www.cmegroup.com/trading/equity-index/rolldates.html",
        "https://www.cmegroup.com/rulebook/NYMEX/2/200.pdf",
        "https://www.cmegroup.com/markets/metals/precious/gold.contractSpecs.html",
        "https://www.cmegroup.com/rulebook/COMEX/1a/113.pdf",
        "https://www.cmegroup.com/trading/interest-rates/files/ir-roll-description.pdf",
        "https://ninjatrader.com/futures/futures-contracts/energy/crude-oil/",
        "https://ninjatrader.com/futures/futures-contracts/metals/gold/",
        (
            "https://help.metrotrade.com/kb/"
            "10-year-u.s.-treasury-note-futures-zn-contract-specifications"
        ),
    ],
    "unresolved": [
        (
            "ES/NQ roll: CME 'Monday prior to the third Friday' (used) vs "
            "trade press 'Thursday ~8 days before' (recorded, not used)"
        ),
        (
            "GC active months: CME TAS list G/J/M/Q/Z (used) vs third-party "
            "sets that add V (October)"
        ),
        (
            "CL and GC roll leads: no exchange-published roll date found for "
            "either; broker figures conflict"
        ),
    ],
}


# ---------------------------------------------------------------------------
# Reading the upstream artifact
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Row:
    product_group: str
    date: str
    eth_open_utc: str
    eth_close_utc: str


def _parse_utc(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def _fmt_utc(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_sessions() -> dict[str, list[_Row]]:
    by_group: dict[str, list[_Row]] = defaultdict(list)
    with UPSTREAM_SESSIONS.open(newline="") as f:
        for row in csv.DictReader(f):
            by_group[row["product_group"]].append(
                _Row(
                    product_group=row["product_group"],
                    date=row["date"],
                    eth_open_utc=row["eth_open_utc"],
                    eth_close_utc=row["eth_close_utc"],
                )
            )
    for rows in by_group.values():
        rows.sort(key=lambda r: r.date)
    return dict(by_group)


def _load_holidays() -> dict[str, set[str]]:
    holidays: dict[str, set[str]] = defaultdict(set)
    with UPSTREAM_RECONCILIATION.open(newline="") as f:
        for row in csv.DictReader(f):
            if row["event_type"] == "HOLIDAY":
                holidays[row["product_group"]].add(row["date"])
    return dict(holidays)


# ---------------------------------------------------------------------------
# Break-window derivation
# ---------------------------------------------------------------------------


def _classify_break(prev_date: date, next_date: date, group_holidays: set[str]) -> str:
    """Classify the closed gap between two consecutive sessions.

    Derived from three measurable facts — the number of calendar days skipped,
    whether every skipped day is a Saturday/Sunday, and whether the
    reconciliation artifact records a HOLIDAY on any skipped day. Nothing is
    assumed about exchange policy.
    """
    skipped = [
        prev_date + timedelta(days=n) for n in range(1, (next_date - prev_date).days)
    ]
    if any(d.isoformat() in group_holidays for d in skipped):
        return CLASS_HOLIDAY
    if not skipped:
        return CLASS_DAILY
    if all(d.weekday() >= 5 for d in skipped):
        return CLASS_WEEKEND
    return CLASS_UNCLASSIFIED


def build_break_windows(
    sessions: dict[str, list[_Row]], holidays: dict[str, set[str]]
) -> list[dict]:
    """One row per inter-session gap, per product group."""
    rows: list[dict] = []
    for group, group_rows in sorted(sessions.items()):
        group_holidays = holidays.get(group, set())
        for prev, nxt in pairwise(group_rows):
            start = _parse_utc(prev.eth_close_utc)
            end = _parse_utc(nxt.eth_open_utc)
            if end <= start:
                # The vendored artifact says the next session opens at or
                # before the previous one closed: there is no closed window to
                # emit. Recorded by omission rather than emitted as a
                # zero/negative-length window, which no `now in window` test
                # could act on.
                continue
            rows.append(
                {
                    "product_group": group,
                    "date": prev.date,
                    "break_start_utc": _fmt_utc(start),
                    "break_end_utc": _fmt_utc(end),
                    "break_class": _classify_break(
                        date.fromisoformat(prev.date),
                        date.fromisoformat(nxt.date),
                        group_holidays,
                    ),
                }
            )
    return rows


# ---------------------------------------------------------------------------
# Roll-schedule derivation
# ---------------------------------------------------------------------------


def _business_days(group_rows: list[_Row]) -> list[date]:
    """The group's own session dates — the ONLY business-day calendar used.

    "3 business days before the 25th" is meaningless without a business-day
    calendar, and inventing one (weekdays-minus-a-holiday-list) would put a
    second, unreconciled holiday calendar in the tree next to the vendored one
    (C.9). The group's own trading dates ARE that calendar, already
    reconciled.
    """
    return [date.fromisoformat(r.date) for r in group_rows]


def _business_days_before(days: list[date], anchor: date, n: int) -> date | None:
    """The session date `n` business days before `anchor`, or None if off-span.

    `anchor` itself counts as day 0 when it is a session date; when it is not,
    counting starts from the last session date preceding it. Both readings are
    needed, and they are the two halves of NYMEX's own wording for CL: *3
    business days before the 25th*, and *where the 25th is not a business day,
    3 business days prior to the last business day preceding the 25th*.
    """
    before = len([d for d in days if d < anchor])
    anchor_is_session = before < len(days) and days[before] == anchor
    base = before if anchor_is_session else before - 1
    target = base - n
    if target < 0 or target >= len(days):
        return None
    return days[target]


def _first_notice_day(days: list[date], year: int, month: int) -> date | None:
    """The last session date before the delivery month starts.

    For the physically-delivered contracts this is First Notice Day (CL, GC)
    / First Position Day (ZN), and it is a HARD exchange date rather than a
    convention — which is why the two rules that could be anchored on it are.
    """
    first_of_month = date(year, month, 1)
    earlier = [d for d in days if d < first_of_month]
    return earlier[-1] if earlier else None


def _third_friday(year: int, month: int) -> date:
    d = date(year, month, 1)
    fridays = 0
    while True:
        if d.weekday() == 4:
            fridays += 1
            if fridays == 3:
                return d
        d += timedelta(days=1)


def _last_trading_date(
    rule: str, year: int, month: int, days: list[date]
) -> date | None:
    """The contract's last trading date under `rule`, in the delivery month."""
    if rule == "third_friday":
        return _third_friday(year, month)
    if rule == "nymex_cl_ltd":
        # 3 business days before the 25th calendar day of the PRECEDING month.
        prev_year, prev_month = (year, month - 1) if month > 1 else (year - 1, 12)
        return _business_days_before(days, date(prev_year, prev_month, 25), 3)
    if rule == "comex_gc_ltd":
        # 3rd-last business day of the delivery month.
        in_month = [d for d in days if d.year == year and d.month == month]
        return in_month[-3] if len(in_month) >= 3 else None
    if rule == "cbot_note_ltd":
        # The 7th business day PRECEDING the last business day of the month:
        # in_month[-1] is that last business day, so the 7th preceding it is
        # seven positions earlier.
        in_month = [d for d in days if d.year == year and d.month == month]
        return in_month[-8] if len(in_month) >= 8 else None
    raise ValueError(f"unknown ltd_rule {rule!r}")


def _roll_day(rule: RollRule, year: int, month: int, days: list[date], ltd: date):
    """The calendar day front-month identity moves off this contract."""
    if rule.roll_anchor == "ltd":
        return ltd - timedelta(days=rule.roll_lead_days)
    if rule.roll_anchor == "fnd":
        fnd = _first_notice_day(days, year, month)
        return None if fnd is None else fnd - timedelta(days=rule.roll_lead_days)
    raise ValueError(f"unknown roll_anchor {rule.roll_anchor!r}")


def _contracts_for(
    symbol: str, rule: RollRule, days: list[date]
) -> list[tuple[str, date, date]]:
    """(contract, roll_day, last_trading_day) for every contract in the span."""
    contracts: list[tuple[str, date, date]] = []
    for year in range(days[0].year, days[-1].year + 1):
        for month in range(1, 13):
            if MONTH_CODE[month - 1] not in rule.months:
                continue
            ltd = _last_trading_date(rule.ltd_rule, year, month, days)
            if ltd is None:
                continue
            roll_at = _roll_day(rule, year, month, days, ltd)
            if roll_at is None:
                continue
            contracts.append(
                (f"{symbol}{MONTH_CODE[month - 1]}{year % 100:02d}", roll_at, ltd)
            )
    contracts.sort(key=lambda c: c[1])
    return contracts


def _roll_rows(
    symbol: str,
    rule: RollRule,
    contracts: list[tuple[str, date, date]],
    close_by_date: dict[str, str],
    days: list[date],
) -> list[dict]:
    """One row per contract, each starting where its predecessor rolled.

    The FIRST contract in the span is dropped rather than given a fabricated
    start: §7.5's roll instant is a defined boundary, and a made-up one is
    exactly the phantom seam it forbids.
    """
    rule_text = (
        f"months={rule.months} ltd={rule.ltd_rule} "
        f"roll_anchor={rule.roll_anchor} roll_lead_days={rule.roll_lead_days}"
    )
    rows: list[dict] = []
    for prev, current in pairwise(contracts):
        contract, roll_day, ltd = current
        roll_close = _resolve_close(close_by_date, days, roll_day)
        front_from_close = _resolve_close(close_by_date, days, prev[1])
        if roll_close is None or front_from_close is None:
            continue
        rows.append(
            {
                "symbol": symbol,
                "contract": contract,
                "front_from_utc": front_from_close,
                "roll_at_utc": roll_close,
                "last_trading_date": ltd.isoformat(),
                "rule": rule_text,
                "source": rule.source,
                "high_risk": "1",
            }
        )
    return rows


def build_roll_schedule(sessions: dict[str, list[_Row]]) -> list[dict]:
    """§7.5's per-symbol front-month schedule, rule-derived and PROVISIONAL."""
    rows: list[dict] = []
    for symbol, (group, _src) in sorted(SYMBOL_PRODUCT_GROUP.items()):
        rule = ROLL_RULES[symbol]
        group_rows = sessions[group]
        days = _business_days(group_rows)
        close_by_date = {r.date: r.eth_close_utc for r in group_rows}
        contracts = _contracts_for(symbol, rule, days)
        rows += _roll_rows(symbol, rule, contracts, close_by_date, days)
    return rows


def _resolve_close(
    close_by_date: dict[str, str], days: list[date], day: date
) -> str | None:
    """The session close (UTC) on `day`, or on the last session before it.

    §7.5 fixes a DEFINED roll instant; anchoring it to a session close keeps
    it inside a closed window (no position can span it — the intraday-only
    mandate of §6.1b), and rolling back to the previous session when the
    computed day is a holiday keeps it a real instant rather than a nominal
    one.
    """
    if day.isoformat() in close_by_date:
        return close_by_date[day.isoformat()]
    earlier = [d for d in days if d < day]
    if not earlier:
        return None
    return close_by_date[earlier[-1].isoformat()]


# ---------------------------------------------------------------------------
# Emit
# ---------------------------------------------------------------------------


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _sha256(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for p in paths:
        h.update(p.read_bytes())
    return h.hexdigest()


def main() -> None:
    """Generate, write, and hash-stamp the three extension artifacts."""
    sessions = _load_sessions()
    holidays = _load_holidays()
    upstream = json.loads(UPSTREAM_PROVENANCE.read_text())

    # The chain's near end, computed from BYTES, not read from the stamp: if
    # the upstream artifact was edited and its own stamp re-issued to match,
    # this extension's stamp still disagrees and `check_calendar_schema`
    # reddens. That is the whole reason the chain is recorded.
    upstream_recomputed = _sha256([UPSTREAM_SESSIONS, UPSTREAM_RECONCILIATION])

    symbol_rows = [
        {"symbol": s, "product_group": g, "source": src}
        for s, (g, src) in sorted(SYMBOL_PRODUCT_GROUP.items())
    ]
    break_rows = build_break_windows(sessions, holidays)
    roll_rows = build_roll_schedule(sessions)

    _write_csv(SYMBOL_MAP_FILE, SYMBOL_MAP_FIELDS, symbol_rows)
    _write_csv(BREAK_WINDOWS_FILE, BREAK_FIELDS, break_rows)
    _write_csv(ROLL_SCHEDULE_FILE, ROLL_FIELDS, roll_rows)

    class_counts: dict[str, int] = {}
    for r in break_rows:
        class_counts[r["break_class"]] = class_counts.get(r["break_class"], 0) + 1

    provenance = {
        "content_hash_sha256": _sha256(
            [SYMBOL_MAP_FILE, BREAK_WINDOWS_FILE, ROLL_SCHEDULE_FILE]
        ),
        "content_hash_covers": [
            SYMBOL_MAP_FILE.name,
            BREAK_WINDOWS_FILE.name,
            ROLL_SCHEDULE_FILE.name,
        ],
        "content_hash_excludes": [EXT_PROVENANCE_FILE.name, "generated_utc"],
        "generated_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generator": "scripts/crucible/calendar_ext_gen.py",
        "generator_dependencies": "python stdlib only",
        "upstream_artifact": [UPSTREAM_SESSIONS.name, UPSTREAM_RECONCILIATION.name],
        "upstream_content_hash_sha256": upstream_recomputed,
        "upstream_stamped_hash_sha256": upstream.get("content_hash_sha256"),
        "upstream_span": upstream.get("span"),
        "row_counts": {
            SYMBOL_MAP_FILE.name: len(symbol_rows),
            BREAK_WINDOWS_FILE.name: len(break_rows),
            ROLL_SCHEDULE_FILE.name: len(roll_rows),
        },
        "break_class_counts": class_counts,
        "roll_schedule_status": (
            "PROVISIONAL — rule-derived from the vendored session calendar, "
            "every row high_risk=1. §7.5 sources the live roll schedule from "
            "the calendar poller (front month = volume leader), which no "
            "offline artifact can observe. Replacing these rows is a data "
            "swap: the schema and every reader are unchanged."
        ),
        "roll_schedule_sources": ROLL_SOURCE_NOTES,
        "utc_canonical": (
            "every column named *_utc is a UTC instant in ...Z form; no "
            "exchange-local column appears in any file this stamp covers "
            "(§12.3 — exchange-local is converted exactly once at window "
            "generation and never stored on a decision path)"
        ),
    }
    EXT_PROVENANCE_FILE.write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n"
    )

    print(f"wrote {SYMBOL_MAP_FILE} ({len(symbol_rows)} rows)")
    print(f"wrote {BREAK_WINDOWS_FILE} ({len(break_rows)} rows) {class_counts}")
    print(f"wrote {ROLL_SCHEDULE_FILE} ({len(roll_rows)} rows)")
    print(f"wrote {EXT_PROVENANCE_FILE}")
    print(f"content_hash_sha256={provenance['content_hash_sha256']}")
    print(f"upstream_content_hash_sha256={upstream_recomputed}")


if __name__ == "__main__":
    main()
