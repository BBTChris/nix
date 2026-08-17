"""§9's positions PROJECTION — the fold over `plane1_event_log`, and its rebuild.

Every `§` in this module cites `docs/nics_risk_subsystem_spec_v1.3.md`, the frozen
risk spec, unless another document is named on the same line. Schema authority:
`databases/schema/plane1.sql` and `docs/nix_plane1_schema_spec.md` (ARC 035 /
Phase 0.4, frozen). ARC 035 / Stage 1 / sub-agent B (B1).

§9, verbatim and entire:

    Positions table = projection (rebuildable; dashboard + reconciliation read it).

------------------------------------------------------------------------------
WHAT "REBUILDABLE" HAS TO MEAN TO BE FALSIFIABLE
------------------------------------------------------------------------------
"Rebuildable" is a property of a PAIR: a log, and a table that can be destroyed
and reconstructed from it to the same state. Neither half alone is testable. So
this module ships the fold as a PURE FUNCTION over log rows — `fold_events` reads
no database at all — and the rebuild as `TRUNCATE`-then-write. A fold that could
read `plane1_positions` while rebuilding `plane1_positions` would be seeded by
the thing it claims to derive, and every rebuild would "match" trivially.

The brief's §0a is the other half of the same point: **an empty-log rebuild proves
nothing.** An empty log folds to an empty projection, which equals the empty
projection that was dropped, and every assertion passes. `MIN_FOLDED_EVENTS`
below is the floor a caller can assert against; the gate treats a log under it as
CANNOT_MEASURE rather than PASS.

------------------------------------------------------------------------------
ORDERING IS `wal_seq`, NOT `event_id` — AND THAT IS LOAD-BEARING
------------------------------------------------------------------------------
The schema spec §2.2 is explicit: *"the WAL is the only place ordering is
authoritative. Postgres commit order under group-commit is BATCH order, and
`event_id` is assigned at INSERT and not at enqueue, so neither is a safe
ordering key."*

So the fold orders by `(wal_seq, event_id)` — `wal_seq` first because it is
enqueue order, `event_id` second only to make the sort total when a fixture or a
replay reuses a sequence number. A fold ordered by `event_id` alone would produce
a DIFFERENT projection from the same log after a reconnect flush, because a
buffered batch commits after rows that happened later. `test_plane1_projection`
drives exactly that: a log whose `event_id` order is the reverse of its `wal_seq`
order must fold to the same projection.

The watermark written to `plane1_projection_meta.rebuilt_through_event_id` is the
MAXIMUM `event_id` folded, not the maximum `wal_seq`: the watermark answers *"is
there a row in Postgres this projection has not seen?"*, and that question is
about the table's own key.

------------------------------------------------------------------------------
THE WRITE PATH IS THE LIMITER'S ROLE, AND NOTHING HERE WRITES THE LOG
------------------------------------------------------------------------------
§12.10: *"Limiter sole writer. No new writers, ever."* This module writes
`plane1_positions` and `plane1_projection_meta` and NEVER `plane1_event_log`. It
does so under `SET ROLE nix_limiter`, which is a real privilege drop even from a
superuser session, so the database itself refuses anything this module has no
business doing — including the log INSERT it never attempts.

That asymmetry is the schema's design and `check_plane1_schema` ARM 4/ARM 7/ARM 9
already prove it: the Limiter holds `UPDATE`/`DELETE`/`TRUNCATE` on the
projection and holds NONE of them on the log. The rebuild is only possible
because of the grant, and the record is only safe because of its absence.

------------------------------------------------------------------------------
WHAT THIS MODULE DOES NOT DO — stated so no green here implies it
------------------------------------------------------------------------------
* It does not write `plane1_event_log`. Getting rows INTO the log is the
  Limiter's `enqueue -> WAL -> group-commit` path (`nixrisk/wal.py`) and the
  Postgres commit sink that lands it; that sink is ARC 035 sub-agent A's.
* **Nothing in this tree emits a `filled` event.** `nixrisk/seam.py`'s `EventKind`
  says so in its own docstring (*"STILL OMITTED … `filled`"*), and `filled` is the
  event this fold is mostly a fold OF. The fold is proven here against real log
  rows; the production wiring that would feed it is NOT built, and no green in
  this module may be read as saying it is.
* It is not an incremental fold. Every rebuild re-reads the whole log. At Plane-1
  volumes (human-scale transitions, §11's own framing) that is correct and
  simple; an incremental fold would need its own correctness argument about
  exactly the crash gap this arc exists to heal.
"""

from __future__ import annotations

# pylint: disable=duplicate-code
# R0801 across this arc's Plane-1 modules pairs their DECLARATION BLOCKS,
# their `psql` subprocess helpers and their scratch-cluster fixtures. That
# shape is REQUIRED, not accidental: §4.2 makes every check independently
# runnable and self-contained, and four sub-agents wrote against the same
# frozen schema in worktrees that could not see each other. The same
# reasoning a dozen existing checks already state at this exact site.
# pylint: disable=too-many-instance-attributes
# These are the PROJECTION's row shapes. `plane1_positions` has twelve columns
# (databases/schema/plane1.sql, frozen ARC 035 Phase 0.4) and a dataclass that
# mirrors a table row honestly has one attribute per column. Splitting them to
# satisfy a counter would put half a row in one object and half in another.
import dataclasses
import json
import shutil
import subprocess  # nosec B404 - psql IS the instrument; §9.1 forbids new deps
from collections.abc import Iterable, Mapping, Sequence
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from nixrisk.seam import PositionRow, PositionState

#: The live Plane-1 database. Named here rather than imported from the gate so
#: this module does not depend on `checks/`; the gate asserts they agree.
PLANE1_DB = "nix_plane1"

#: The role every write below runs as. §12.10's sole writer, by identity.
WRITER_ROLE = "nix_limiter"

#: Below this many POSITION-AFFECTING events, a rebuild comparison is a
#: statement about an almost-empty set. The brief's §0a: *"an empty-log rebuild
#: proves nothing."* Callers that certify a rebuild assert against this. It is a
#: FLOOR and not a target: the shipped fixture carries thirteen.
MIN_FOLDED_EVENTS = 8

#: Dollar-quoting tag for every literal this module hands to psql. JSON produced
#: by `json.dumps` cannot contain it (`$` is not escaped, but the tag as a whole
#: never appears in a JSON serialisation of the values here); `_dollar_quote`
#: asserts that rather than assuming it.
_TAG = "p1proj"

STATE_OPEN = "open"
STATE_PARTIAL = "partial"
STATE_CLOSED = "closed"

#: The event types that MOVE a position. Everything else in §12.10's inventory
#: is money-gating or diagnostic but does not change size.
EVENT_FILLED = "filled"
EVENT_CANCEL = "cancel"
EVENT_CLOSED = "closed"
EVENT_PROTECTIVE_EXIT = "protective_exit"
EVENT_SENTINEL_FLATTEN = "sentinel_flatten"

POSITION_AFFECTING: frozenset[str] = frozenset(
    {
        EVENT_FILLED,
        EVENT_CANCEL,
        EVENT_CLOSED,
        EVENT_PROTECTIVE_EXIT,
        EVENT_SENTINEL_FLATTEN,
    }
)

#: The other thirteen §12.10 Plane-1 events, ENUMERATED rather than defaulted.
#:
#: A fold that quietly ignored anything it did not recognise would silently
#: ignore a NEW event type someone adds to `plane1_event_enum` — and the new
#: type is exactly the case where a fold decision is owed. So the classification
#: is total and closed: `POSITION_AFFECTING | POSITION_NEUTRAL` must equal the
#: schema's enum, both directions, and `check_plane1_projection` ARM 1 proves it
#: against the live catalog.
POSITION_NEUTRAL: frozenset[str] = frozenset(
    {
        "signal",
        "accepted",
        "denied",
        "exit_intent",
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

CLASSIFIED: frozenset[str] = POSITION_AFFECTING | POSITION_NEUTRAL

#: §9's documented "this event has no trade" sentinel (schema spec §2.2).
NO_TRADE = "-"

#: NUMERIC(18,8) — the projection's own scale. The fold quantizes to it so a
#: re-fold in Python and a round trip through Postgres cannot disagree in the
#: eighth decimal place and look like drift.
_SCALE = Decimal("0.00000001")


class ProjectionError(RuntimeError):
    """Base for every refusal here."""


class ProjectionUnavailable(ProjectionError):
    """The database could not be reached — §17, never a PASS."""


# ---------------------------------------------------------------------------
# psql, as a subprocess. There is no Python Postgres driver in the venv and
# §9.1 forbids adding one.
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Psql:
    """One connection target. `host` may be a UNIX socket DIRECTORY.

    The socket-directory form is what lets the crash drill point this at its own
    ephemeral cluster (`initdb` + `pg_ctl -k <dir> -c listen_addresses=''`)
    without touching the system cluster three sibling agents are on.
    """

    dbname: str
    host: str | None = None
    port: int | None = None
    timeout_s: float = 120.0

    def _argv(self, *extra: str) -> list[str]:
        binary = shutil.which("psql")
        if binary is None:
            raise ProjectionUnavailable("psql is not on PATH")
        argv = [binary, "-d", self.dbname, "-qAt", "-v", "ON_ERROR_STOP=1"]
        if self.host is not None:
            argv += ["-h", self.host]
        if self.port is not None:
            argv += ["-p", str(self.port)]
        return argv + list(extra)

    def run(self, sql: str, *, verbose: bool = False) -> tuple[int, str, str]:
        """Execute `sql`. Returns `(rc, stdout, stderr)`; never raises on rc."""
        extra = ["-v", "VERBOSITY=verbose"] if verbose else []
        proc = subprocess.run(  # nosec B603 - fixed argv, no shell
            self._argv(*extra, "-c", sql),
            capture_output=True,
            text=True,
            timeout=self.timeout_s,
            check=False,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()

    def must(self, sql: str) -> str:
        """Execute `sql` and require success. Anything else is unmeasurable."""
        rc, out, err = self.run(sql)
        if rc != 0:
            raise ProjectionUnavailable(
                f"{self.dbname}: `{sql.strip()[:70]}...` -> rc={rc}: {err[-400:]}"
            )
        return out

    def rows(self, sql: str) -> list[dict[str, Any]]:
        """A SELECT wrapped in `json_agg`, decoded. `[]` when it matched nothing.

        JSON rather than psql's `-A` column separator on purpose: `reason` is
        free text written by the Limiter and a `|` inside it would silently
        shift every field to its right, which is a decoding bug that reads as
        drift.
        """
        payload = self.must(sql)
        return list(json.loads(payload) if payload else [])


def _dollar_quote(text: str) -> str:
    """`$tag$text$tag$`, with the tag's absence ASSERTED, not assumed."""
    fence = f"${_TAG}$"
    if fence in text:  # pragma: no cover - defensive; see the assertion below
        raise ProjectionError(
            f"refusing to build a literal containing its own dollar-quote tag "
            f"{fence!r}; the value would terminate the quote early"
        )
    return f"{fence}{text}{fence}"


# ---------------------------------------------------------------------------
# The rows, as the fold sees them
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class LogEvent:
    """One `plane1_event_log` row, decoded. Immutable — the fold never edits one."""

    event_id: int
    wal_seq: int
    occurred_at: str
    event_type: str
    strategy_id: str
    trade_id: str
    reason: str
    symbol: str | None
    natural_key: str
    payload: Mapping[str, Any]

    @property
    def order_key(self) -> tuple[int, int]:
        """`(wal_seq, event_id)` — enqueue order, made total. See the docstring."""
        return (self.wal_seq, self.event_id)


@dataclasses.dataclass(frozen=True)
class ProjectedPosition:
    """One row of `plane1_positions`, as the FOLD computes it.

    Field-for-field with the table, so a comparison between what the fold says
    and what the database holds is a comparison of the same shape rather than a
    summary of one against a summary of the other.
    """

    trade_id: str
    strategy_id: str
    symbol: str
    side: str
    state: str
    qty_open: int
    qty_filled: int
    avg_entry_price: Decimal | None
    stop_distance: Decimal | None
    opened_at: str | None
    closed_at: str | None
    last_event_id: int

    def as_json_row(self) -> dict[str, Any]:
        """The shape `json_populate_recordset(NULL::plane1_positions, …)` wants."""
        return {
            "trade_id": self.trade_id,
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "side": self.side,
            "state": self.state,
            "qty_open": self.qty_open,
            "qty_filled": self.qty_filled,
            "avg_entry_price": _text(self.avg_entry_price),
            "stop_distance": _text(self.stop_distance),
            "opened_at": self.opened_at,
            "closed_at": self.closed_at,
            "last_event_id": self.last_event_id,
        }


@dataclasses.dataclass(frozen=True)
class FoldResult:
    """What one fold produced, plus what it could not make sense of.

    `anomalies` is not decoration. A log the fold cannot interpret — an exit for
    a trade that never filled, a fill with no quantity — is a finding about the
    RECORD, and a fold that silently skipped those rows would turn a corrupt log
    into a clean-looking projection.
    """

    positions: tuple[ProjectedPosition, ...]
    through_event_id: int
    folded_events: int
    position_events: int
    anomalies: tuple[str, ...]


def _text(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def _decimal(payload: Mapping[str, Any], key: str) -> Decimal | None:
    raw = payload.get(key)
    if raw is None or raw == "":
        return None
    try:
        return Decimal(str(raw)).quantize(_SCALE, rounding=ROUND_HALF_UP)
    except InvalidOperation, ValueError:
        return None


def _int(payload: Mapping[str, Any], key: str) -> int | None:
    raw = payload.get(key)
    if raw is None or raw == "":
        return None
    try:
        return int(str(raw))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# The fold itself. PURE — no database, no clock, no I/O.
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class _Build:
    """Mutable accumulator for one trade. Never leaves this module."""

    trade_id: str
    strategy_id: str = ""
    symbol: str = ""
    side: str = ""
    state: str = STATE_PARTIAL
    qty_open: int = 0
    qty_filled: int = 0
    #: The size the entry ASKED for. §4: a partial fill sets the position to the
    #: actual filled quantity and cancels the remainder, so this is what tells
    #: `partial` (remainder unresolved) from `open` (remainder resolved). It is
    #: fold state and NOT a projection column: the projection records what IS,
    #: and the log records what was asked.
    requested: int = 0
    avg_entry_price: Decimal | None = None
    stop_distance: Decimal | None = None
    opened_at: str | None = None
    closed_at: str | None = None
    last_event_id: int = 0

    def frozen(self) -> ProjectedPosition:
        """This mutable fold-state as an immutable row.

        The fold mutates while it walks the log; what it HANDS BACK must
        not, or a caller holding a projection could change it and the
        comparison against the pre-drop snapshot would compare an object
        with itself.
        """
        return ProjectedPosition(
            trade_id=self.trade_id,
            strategy_id=self.strategy_id,
            symbol=self.symbol,
            side=self.side,
            state=self.state,
            qty_open=self.qty_open,
            qty_filled=self.qty_filled,
            avg_entry_price=self.avg_entry_price,
            stop_distance=self.stop_distance,
            opened_at=self.opened_at,
            closed_at=self.closed_at,
            last_event_id=self.last_event_id,
        )


def _on_fill(build: _Build, event: LogEvent) -> list[str]:
    """A confirmed fill (§4: OPEN is asserted only on broker fill confirmation)."""
    qty = _int(event.payload, "qty")
    price = _decimal(event.payload, "price")
    if qty is None or qty <= 0:
        return [
            (
                f"event {event.event_id} ({EVENT_FILLED}, trade {event.trade_id}) "
                f"carries qty={event.payload.get('qty')!r} — a fill with no positive "
                f"quantity moves nothing and cannot be folded"
            )
        ]
    if build.state == STATE_CLOSED:
        return [
            (
                f"event {event.event_id} fills trade {event.trade_id} AFTER it closed "
                f"at {build.closed_at} — the projection cannot represent a reopened "
                f"round trip and §4 mints a new trade_id at each open"
            )
        ]
    if build.qty_filled == 0:
        build.strategy_id = event.strategy_id
        build.symbol = event.symbol or str(event.payload.get("symbol") or "")
        build.side = str(event.payload.get("side") or "")
        build.opened_at = event.occurred_at
        build.stop_distance = _decimal(event.payload, "stop_distance")
        build.requested = _int(event.payload, "qty_requested") or qty
    if price is not None:
        prior = build.avg_entry_price or Decimal(0)
        total = prior * build.qty_filled + price * qty
        build.avg_entry_price = (total / (build.qty_filled + qty)).quantize(
            _SCALE, rounding=ROUND_HALF_UP
        )
    build.qty_filled += qty
    build.qty_open += qty
    build.state = STATE_OPEN if build.qty_filled >= build.requested else STATE_PARTIAL
    return []


def _on_cancel(build: _Build, event: LogEvent) -> list[str]:
    """The IOC remainder-cancel (§4). It RESOLVES a partial; it moves no size."""
    if build.qty_filled == 0:
        return [
            (
                f"event {event.event_id} ({EVENT_CANCEL}) resolves trade "
                f"{event.trade_id}, which has no fill — nothing to resolve"
            )
        ]
    if build.state == STATE_PARTIAL:
        #: §4: *"Limiter sets position = ACTUAL FILLED QTY, cancels the unfilled
        #: remainder."* Once the remainder is cancelled the position is what it
        #: is, so the asked-for size stops being the yardstick.
        build.requested = build.qty_filled
        build.state = STATE_OPEN
    return []


def _on_reduce(build: _Build, event: LogEvent) -> list[str]:
    """An exit: `closed`, `protective_exit` or `sentinel_flatten`.

    `closed` is TERMINAL by §9's own wording (*"closed — round trip complete"*)
    and takes the position flat whatever quantity it names. `protective_exit` and
    `sentinel_flatten` may be scale-outs, so they reduce by the quantity they
    carry and default to the whole remaining position when they carry none — the
    fail-closed default, because a flatten with an unreadable quantity that left
    size behind would understate live exposure.
    """
    if build.qty_filled == 0:
        return [
            (
                f"event {event.event_id} ({event.event_type}) exits trade "
                f"{event.trade_id}, which never filled — an exit before any open"
            )
        ]
    if build.state == STATE_CLOSED:
        return [
            (
                f"event {event.event_id} ({event.event_type}) exits trade "
                f"{event.trade_id}, already closed at {build.closed_at}"
            )
        ]
    qty = _int(event.payload, "qty")
    if event.event_type == EVENT_CLOSED or qty is None or qty >= build.qty_open:
        build.qty_open = 0
    else:
        build.qty_open -= qty
    if build.qty_open == 0:
        build.state = STATE_CLOSED
        build.closed_at = event.occurred_at
    else:
        build.state = STATE_OPEN
        build.requested = build.qty_filled
    return []


_HANDLERS = {
    EVENT_FILLED: _on_fill,
    EVENT_CANCEL: _on_cancel,
    EVENT_CLOSED: _on_reduce,
    EVENT_PROTECTIVE_EXIT: _on_reduce,
    EVENT_SENTINEL_FLATTEN: _on_reduce,
}


def fold_events(events: Iterable[LogEvent]) -> FoldResult:
    """Fold the log into the positions projection. PURE: no database, no clock.

    Ordering is `(wal_seq, event_id)` and is imposed HERE rather than trusted
    from the caller, so a caller that read the log in commit order still gets
    the enqueue-order fold. See the module docstring for why that matters.
    """
    ordered = sorted(events, key=lambda e: e.order_key)
    builds: dict[str, _Build] = {}
    anomalies: list[str] = []
    position_events = 0
    through = 0
    for event in ordered:
        through = max(through, event.event_id)
        if event.event_type not in CLASSIFIED:
            anomalies.append(
                f"event {event.event_id} carries type {event.event_type!r}, which "
                f"this fold has no rule for. A fold that ignored an unknown type "
                f"would silently ignore exactly the event a decision is owed on"
            )
            continue
        handler = _HANDLERS.get(event.event_type)
        if handler is None:
            continue
        position_events += 1
        if event.trade_id == NO_TRADE or not event.trade_id:
            anomalies.append(
                f"event {event.event_id} ({event.event_type}) carries the "
                f"no-trade sentinel {NO_TRADE!r}; a position event with no trade "
                f"cannot be attributed"
            )
            continue
        build = builds.setdefault(event.trade_id, _Build(trade_id=event.trade_id))
        anomalies += handler(build, event)
        build.last_event_id = event.event_id
    return FoldResult(
        #: A trade only becomes a POSITION once something filled (§4: *"Open is
        #: asserted ONLY on broker fill confirmation"*). A trade_id that reached
        #: the fold and never filled — an exit for a trade that never opened —
        #: is an ANOMALY and is reported as one; emitting it as a zero-fill row
        #: would put a phantom position in the table reconciliation reads, which
        #: is the failure this projection exists to make impossible. Found by
        #: `test_an_exit_before_any_fill_is_an_ANOMALY_not_a_silent_skip`, which
        #: was written for the anomaly and caught the phantom row instead.
        positions=tuple(
            builds[key].frozen() for key in sorted(builds) if builds[key].qty_filled > 0
        ),
        through_event_id=through,
        folded_events=len(ordered),
        position_events=position_events,
        anomalies=tuple(anomalies),
    )


# ---------------------------------------------------------------------------
# Reading and writing the real tables
# ---------------------------------------------------------------------------

_LOG_SELECT = """
select coalesce(json_agg(t order by t.wal_seq, t.event_id)::text, '[]')
from (
  select event_id, wal_seq, occurred_at::text as occurred_at,
         event_type::text as event_type, strategy_id, trade_id, reason,
         symbol, natural_key, payload
  from plane1_event_log
) t
"""

_PROJECTION_SELECT = """
select coalesce(json_agg(t order by t.trade_id)::text, '[]')
from (
  select trade_id, strategy_id, symbol, side, state::text as state,
         qty_open, qty_filled,
         avg_entry_price::text as avg_entry_price,
         stop_distance::text as stop_distance,
         opened_at::text as opened_at, closed_at::text as closed_at,
         last_event_id
  from plane1_positions
) t
"""

_META_SELECT = """
select coalesce(json_agg(t)::text, '[]')
from (
  select id, rebuilt_through_event_id, rebuilt_at::text as rebuilt_at,
         rebuild_source
  from plane1_projection_meta
) t
"""


def read_log(psql: Psql) -> tuple[LogEvent, ...]:
    """Every row of `plane1_event_log`, decoded, in enqueue order."""
    return tuple(
        LogEvent(
            event_id=int(row["event_id"]),
            wal_seq=int(row["wal_seq"]),
            occurred_at=str(row["occurred_at"]),
            event_type=str(row["event_type"]),
            strategy_id=str(row["strategy_id"]),
            trade_id=str(row["trade_id"]),
            reason=str(row["reason"]),
            symbol=row["symbol"],
            natural_key=str(row["natural_key"]),
            payload=dict(row["payload"] or {}),
        )
        for row in psql.rows(_LOG_SELECT)
    )


def read_projection(psql: Psql) -> tuple[dict[str, Any], ...]:
    """`plane1_positions` as stored, by `trade_id`. Every column, as text/int.

    Returned as plain dicts rather than `ProjectedPosition` on purpose: this is
    the side of the comparison that must be *what the database holds*, and
    re-typing it through the fold's own dataclass would let a conversion bug
    cancel itself out on both sides.
    """
    return tuple(psql.rows(_PROJECTION_SELECT))


def read_meta(psql: Psql) -> dict[str, Any]:
    """The singleton watermark row. Raises if the singleton is not singular."""
    rows = psql.rows(_META_SELECT)
    if len(rows) != 1:
        raise ProjectionError(
            f"plane1_projection_meta holds {len(rows)} row(s), not 1 — the "
            f"projection's watermark has no single answer"
        )
    return rows[0]


def projection_row_for(position: ProjectedPosition) -> dict[str, Any]:
    """The stored shape a folded position must equal, for a field-by-field diff."""
    row = position.as_json_row()
    #: Postgres hands `NUMERIC(18,8)` back at full scale and integers as ints;
    #: normalise the fold's side to the same spelling so a diff reports a real
    #: disagreement rather than a formatting one.
    for key in ("avg_entry_price", "stop_distance"):
        if row[key] is not None:
            row[key] = format(Decimal(str(row[key])).quantize(_SCALE), "f")
    return row


def diff_projections(
    folded: Sequence[ProjectedPosition], stored: Sequence[Mapping[str, Any]]
) -> list[str]:
    """FIELD BY FIELD. Returns one line per disagreement; `[]` means identical.

    Not `==` on two containers: a single equality gives a reviewer no way to
    tell "one row differs in one column" from "the rebuild wrote nothing", and
    those are very different findings.
    """
    want = {row["trade_id"]: row for row in (projection_row_for(p) for p in folded)}
    have = {str(row["trade_id"]): dict(row) for row in stored}
    defects: list[str] = []
    for trade_id in sorted(set(want) - set(have)):
        defects.append(
            f"trade {trade_id}: the fold produces a position the projection does"
            f" NOT hold — the projection is behind the log"
        )
    for trade_id in sorted(set(have) - set(want)):
        defects.append(
            f"trade {trade_id}: the projection holds a position no fold of the "
            f"log produces — a row with no events behind it"
        )
    for trade_id in sorted(set(want) & set(have)):
        expected, actual = want[trade_id], have[trade_id]
        for field in sorted(expected):
            left, right = expected[field], _normalise(field, actual.get(field))
            if left != right:
                defects.append(
                    f"trade {trade_id}: field {field} — the fold says {left!r}, "
                    f"the projection holds {right!r}"
                )
    return defects


def _normalise(field: str, value: Any) -> Any:
    """One stored value, spelled the way the fold spells it."""
    if value is None:
        return None
    if field in ("qty_open", "qty_filled", "last_event_id"):
        return int(value)
    if field in ("avg_entry_price", "stop_distance"):
        return format(Decimal(str(value)).quantize(_SCALE), "f")
    return str(value)


@dataclasses.dataclass(frozen=True)
class RebuildReport:
    """One rebuild, recorded. Every number here was measured, none inferred."""

    database: str
    source: str
    log_events: int
    position_events: int
    positions_written: int
    through_event_id: int
    anomalies: tuple[str, ...]
    stored: tuple[dict[str, Any], ...]

    @property
    def measured_enough(self) -> bool:
        """Did the fold see enough of a history to be evidence? (§0a)"""
        return self.position_events >= MIN_FOLDED_EVENTS


def write_projection(
    psql: Psql,
    positions: Sequence[ProjectedPosition],
    *,
    through_event_id: int,
    source: str,
) -> None:
    """TRUNCATE and re-write `plane1_positions`, as `nix_limiter`, in ONE txn.

    One transaction because a projection that is half old and half new is a
    projection nothing can reconcile against, and the window between the
    `TRUNCATE` and the last `INSERT` is exactly when a dashboard would read it.

    `SET ROLE nix_limiter` rather than "we only write the right tables": the
    grant is checked by the executor on every statement, and a rebuild that ran
    as the owner would be able to touch the log by accident and nothing would
    say so.
    """
    payload = json.dumps([p.as_json_row() for p in positions])
    # B608 argued once, here, rather than four times below. Every interpolation
    # in this statement is a MODULE-LEVEL CONSTANT (`WRITER_ROLE`), an `int()`,
    # or a `_dollar_quote`d value whose fence absence is ASSERTED rather than
    # assumed. Nothing reaches it from a caller's SQL, a database row, an
    # environment variable or a file, and it runs as `nix_limiter`, which the
    # database refuses UPDATE/DELETE/TRUNCATE on the log for.
    statement = (
        "BEGIN;\n"  # nosec B608
        f"SET ROLE {WRITER_ROLE};\n"
        "TRUNCATE plane1_positions;\n"
        "INSERT INTO plane1_positions SELECT * FROM "
        f"json_populate_recordset(NULL::plane1_positions, {_dollar_quote(payload)});\n"
        "UPDATE plane1_projection_meta SET "
        f"rebuilt_through_event_id = {int(through_event_id)}, "
        "rebuilt_at = now(), "
        f"rebuild_source = {_dollar_quote(source)} WHERE id = 1;\n"
        "COMMIT;\n"
    )
    rc, _out, err = psql.run(statement, verbose=True)
    if rc != 0:
        raise ProjectionError(f"rebuild write failed on {psql.dbname}: {err[-500:]}")


def rebuild(psql: Psql, *, source: str) -> RebuildReport:
    """§9's rebuild: read the LOG, fold it, replace the projection, read it back.

    The read-back is not decoration and it is not the fold's return value: the
    check contract's rule 2 says a mutation's verdict belongs to an independent
    re-measurement, and a `RebuildReport` built from the in-memory fold would
    report a successful rebuild against a write that never landed.
    """
    events = read_log(psql)
    result = fold_events(events)
    write_projection(
        psql,
        result.positions,
        through_event_id=result.through_event_id,
        source=source,
    )
    stored = read_projection(psql)
    return RebuildReport(
        database=psql.dbname,
        source=source,
        log_events=result.folded_events,
        position_events=result.position_events,
        positions_written=len(stored),
        through_event_id=result.through_event_id,
        anomalies=result.anomalies,
        stored=stored,
    )


def open_positions(stored: Iterable[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    """The rows a reconciliation cares about: everything not `closed`."""
    return tuple(dict(row) for row in stored if str(row["state"]) != STATE_CLOSED)


def position_rows(stored: Iterable[Mapping[str, Any]]) -> tuple[PositionRow, ...]:
    """Stored projection rows as the seam's `PositionRow`, for reconciliation.

    **`margin` is 0.0 and that is deliberate, not a stub.** Margin is a §11 item 3
    RUNNING AGGREGATE maintained on fill/close/tick, not a Plane-1 column: §9's
    log records transitions, and no row in it carries the margin regime that was
    in force. Inventing a number here would put a fabricated money figure into
    the type §3 publishes. Cold-start reconciliation compares SIZES (§4 — the
    true open-position set), never margins, so the field is unused on this path;
    anything that starts reading it must get it from the picture, not from here.
    """
    return tuple(
        PositionRow(
            trade_id=str(row["trade_id"]),
            symbol=str(row["symbol"]),
            strategy_id=str(row["strategy_id"]),
            size=int(row["qty_open"]),
            margin=0.0,
            state=PositionState.OPEN,
            stop_distance=int(Decimal(str(row["stop_distance"] or 0))),
        )
        for row in stored
    )


class PostgresProjection:  # pylint: disable=too-few-public-methods
    """`ColdStart`'s projection port over a REAL Plane-1 database.

    One verb, because §4 gives it one job: re-fold the log and hand cold start
    the positions that fold produces. It is the seam between B1's rebuild and
    B2's reconciliation, and it is deliberately thin — every decision about what
    to DO with a disagreement belongs to §4's reconciler, not here.

    The rebuild happens on EVERY call rather than reading whatever the table
    holds: at cold start the local state is empty and TRUSTLESS (§4), and a
    projection read without re-folding is exactly the stale local state §4 says
    not to trust.
    """

    def __init__(
        self, psql: Psql, *, source: str = "cold-start reconciliation"
    ) -> None:
        self._psql = psql
        self._source = source
        self.last: RebuildReport | None = None
        #: Set by `rebuild`. Recorded rather than enforced: a production log is
        #: routinely below the evidence floor and that is not an error here — it
        #: is a fact a caller may want to report. The FLOOR is a gate's business
        #: (`check_plane1_projection` ARM 2), never a boot's.
        self.measured_enough = False
        #: The watermark the rebuild left behind, read back out of the table.
        self.watermark = 0

    def rebuild(self) -> tuple[PositionRow, ...]:
        """Re-fold the log, replace the projection, VERIFY it, return the OPEN set.

        The verification is not belt-and-braces, it is check-contract rule 2 one
        layer down: **a mutation's verdict belongs to an independent
        re-measurement, never to a return value from the writing path.** So the
        table is re-read and diffed field by field against a FRESH fold of the
        log, and a rebuild that computed a perfect projection and wrote nothing
        raises here instead of handing cold start an empty position set — which
        §4 would read as "provably flat" and admit registration against.
        """
        # ANNOTATED, and the annotation is load-bearing rather than decorative:
        # this method is itself named `rebuild`, so a static reader resolving the
        # call by name alone binds it to the METHOD and infers the wrong return
        # type. `check_uncalled_entry_points` did exactly that and reported
        # `RebuildReport.measured_enough` as having no call site while this line
        # was calling it.
        report: RebuildReport = rebuild(self._psql, source=self._source)
        self.last = report
        self.measured_enough = report.measured_enough
        drift = diff_projections(
            fold_events(read_log(self._psql)).positions, report.stored
        )
        if drift:
            raise ProjectionError(
                f"the rebuilt projection in {self._psql.dbname} does not match a "
                f"fresh fold of its own log: {'; '.join(drift[:4])}"
            )
        #: An event type the fold has no rule for is an event that silently moves
        #: nothing. Checked HERE and not only in the gate, because cold start
        #: reads this projection to decide what to flatten: a silently unfolded
        #: fill is a live position §4 would never see, and §4 never adopts one.
        unruled = sorted(enum_members(self._psql) - CLASSIFIED)
        if unruled:
            raise ProjectionError(
                f"{self._psql.dbname} can record event type(s) the projection "
                f"fold has no rule for: {', '.join(unruled)}. A fold that "
                f"ignored them would report a smaller position set than the log "
                f"describes"
            )
        self.watermark = int(read_meta(self._psql)["rebuilt_through_event_id"])
        return position_rows(open_positions(report.stored))


def enum_members(psql: Psql) -> frozenset[str]:
    """`plane1_event_enum`'s members, read from the catalog."""
    rows = psql.rows(
        "select coalesce(json_agg(t)::text,'[]') from ("
        "select e.enumlabel as label from pg_enum e "
        "join pg_type ty on ty.oid = e.enumtypid "
        "where ty.typname = 'plane1_event_enum') t"
    )
    return frozenset(str(row["label"]) for row in rows)
