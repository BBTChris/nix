#!/usr/bin/env python3
# pylint: disable=duplicate-code
# R0801 pairs this file's DECLARATION BLOCK, its path-keyed loader and its
# `standalone_main` footer against every other house-style check's. That shape
# is REQUIRED, not accidental duplication: the declarations are read STATICALLY
# by AST without importing the check (check contract §4.4), so a shared base
# module would be invisible to `verify.py`'s planner (§4.2).
# pylint: disable=too-many-lines
# C0302: a check is a STANDALONE executable (§4.2) — its arms, its plants and
# its non-vacuity floors live in one file by contract, and splitting them would
# move the can-fail controls away from the arms they bind.
"""Gate: the realized-P&L wire, DRIVEN end to end into real Postgres and back.

ARC 037 / sub-agent A. D3.220, the keystone. Subjects:
`scripts/nixrisk/realized.py` (the arithmetic) and the realizing rows
`scripts/nixrisk/flatten.py` books (the write). Authority read directly from
`docs/nics_risk_subsystem_spec_v1.3.md`: §6.6:429-469 (the realized-P&L EMA and
its locked `(strategy_id, symbol)` key), §6.5:409-410 (commissions and fees
*"debit on close"*), §7:481 (the slippage pad), §9 (the Limiter is the SOLE
Plane-1 writer), §12.10:768 (*"the final trail level rides the `closed` row"* —
the pattern a per-trade figure follows).

## WHAT WAS WRONG

`scripts/nixscore/ema.py` computes §6.6's score from
`plane1_event_log.payload->>'realized_pnl'`, and its own docstring records that
NOTHING IN THIS TREE WROTE THAT KEY. The scorer read a figure the durable record
did not carry, and no gate could see it: a scorer with no input and a scorer at
a healthy cold start produce the same output, which is exactly the observation
`ema.py` refuses to make (`MissingRealized`).

## debug.md §7.12 — WHAT WOULD MAKE THIS GATE PASS WHILE MEASURING NOTHING?

Answered condition by condition, and every door named here is DRIVEN below.

1. **The figure could be the PEAK, not the close.** §6.6:435 — *"a green open
   position can reverse before it closes."* A trade that only ever moves one way
   cannot distinguish them. *Closed:* `_arm_peak` drives a position that goes
   +$150 GREEN WHILE OPEN and CLOSES -$100 RED, and requires the WRITTEN figure
   to equal the CLOSE and to be NEGATIVE. The plant `peak-priced-writer` prices
   the same trade off `TradeFacts.peak_price` and must make that arm FAIL — the
   peak is carried on the facts precisely so the wrong number is constructible.
2. **The figure could be written into a payload nothing reads.** *Closed:*
   `_arm_wire` never reads the figure from the object it wrote. It group-commits
   through the real `Plane1Wal` -> `GroupCommitWriter` -> `Plane1PostgresSink`
   into a scratch database built from the shipped DDL, reads the row back with
   `SELECT`, and folds THAT ROW through `nixscore.ema.realized_closes` /
   `score_pairs`. The EMA must ADVANCE, and the advance is checked against the
   closed form `v1 + alpha*(v2 - v1)` rather than against "it moved".
3. **The reader could be reading a DIFFERENT key.** *Closed:* the negative is
   driven — `realized_pnl` is stripped from the row the DATABASE returned and
   `MissingRealized` must fire and must NAME the key — and `_arm_constants`
   asserts the writer's constants are byte-equal to the scorer's in both
   directions, so a rename on either side is a red here rather than a wire that
   silently parts.
4. **An unrealized mark could leak in.** *Closed:* `_arm_banned` requires no
   `ema.BANNED_UNREALIZED_FIELDS` member on any realizing row read back from
   Postgres, and the plant `banned-field-writer` adds one and must redden it.
5. **One close could be counted TWICE, and every arm above would still pass.**
   `flatten` books TWO realizing-typed rows for one protective close
   (`protective_exit` at the decision, `closed` after reconcile) and
   `ema.daily_advances` SUMS a pair's rows for the day. *Closed:* `_arm_once`
   requires exactly one row per trade to carry a figure and the other to NAME
   its reason; the plant `double-counting-writer` removes the once-only ledger
   and must redden it.
6. **The figure could be the ACCOUNT DELTA wearing a per-trade name.**
   `ScoringSink.book_realized` carries one balance delta for every trade a
   reconcile closed, and §6.6:448 needs one figure per PAIR. *Closed:*
   `_arm_attribution` closes two trades on two symbols in ONE reconcile and
   requires two DIFFERENT figures, neither equal to the account delta.
7. **Postgres could be down and the whole census green over nothing.**
   *Closed:* CANNOT_MEASURE naming the failure (§17), never PASS. Same for an
   import failure and for a plant whose anchor has moved (`PlantFailed`).
8. **Every arm could run zero drives.** *Closed:* `_arm_wire` requires exactly
   `EXPECTED_LANDED` rows read back and at least `MIN_FIGURES` of them carrying
   a figure, and every plant control asserts it changed the outcome rather than
   asserting the outcome alone.

## WHAT THIS GATE DOES NOT PROVE

That any realized figure is being written in PRODUCTION. Nothing in this tree
fills a `TradeFactsBook`: there is no fill feed, `EventKind` still has no
`filled` member, and no daemon constructs a `ProtectiveFlatten`. The wire is
CLOSED and it is not FED, and that gap is CHECK-DEBT (D3.281), not a green here.
It also proves nothing about `sentinel_flatten`, the third member of
`ema.REALIZING_EVENT_TYPES`: no `EventKind` member maps to it (§12.1 marker
replay is unbuilt), so no writer in this tree can emit one.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import importlib
import json
import shutil
import subprocess  # nosec B404 - psql IS the read-back instrument (§9)
import sys
import tempfile
import types
import uuid
from pathlib import Path
from typing import Any, Final

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

# --- orchestration declarations (read statically, never imported) ---
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False
#: Builds and drops its own scratch Plane-1 database, spawns `psql` for the
#: read-back, writes a WAL and a plant tree under `/tmp`, and imports the
#: subject out of `ctx.nix_home`. Declared rather than minimised:
#: `check_observed_resource_claims` compares declarations against OBSERVED
#: claims and the observer is right (§17).
RESOURCES: tuple[str, ...] = (
    "subprocess:psql",
    "subprocess:createdb",
    "subprocess:dropdb",
    "file-write:/tmp",
    "interpreter:sys.modules",
    "interpreter:sys.path",
)
#: `check_plane1_schema` first: this gate builds a scratch database from the
#: shipped DDL and a schema that does not match the spec would make every
#: read-back here a measurement of the wrong table.
DEPENDS_ON: tuple[str, ...] = ("check_plane1_schema",)
#: The artifact this gate MEASURES, for `check_artifact_gate_coverage`.
#: `scripts/nixrisk/flatten.py` is NOT claimed — `check_flatten` owns it and a
#: second claim would be the duplicate instrument doctrine C.9 forbids. Its
#: realizing rows are nevertheless DRIVEN here; coverage and drive are different
#: questions and this gate answers the second for a file another gate names.
SUBJECTS: tuple[str, ...] = ("scripts/nixrisk/realized.py",)
TIME_BOUND = False
EXPECTED_S = 30.0
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "every finding here is a judgement about what a money figure MEANS — a peak "
    "written as a close, a figure counted twice, a mark beside a realization, a "
    "key the reader does not read. There is no mechanical edit that repairs any "
    "of them without deciding what the arithmetic was FOR, and an automated "
    "rewrite of the number that decides which strategy gets the last of the "
    "liquidity is not a repair. A human edits it"
)
INSTALLABLE = False
ON_FAIL = "continue"

NAME = "check_realized_pnl"

REALIZED_FILE = "scripts/nixrisk/realized.py"
FLATTEN_FILE = "scripts/nixrisk/flatten.py"
EMA_FILE = "scripts/nixscore/ema.py"

#: The pair every drive attributes to. Namespaced so a row of this gate's can
#: never be mistaken for a real one in any log it reaches.
STRATEGY = "arc037a_realized"
SYMBOL = "MESU6"

#: Two CONSECUTIVE trading days (a Tuesday and a Wednesday), so the day grid
#: walks exactly ONE step between them and the closed-form advance is exact.
DAY_ONE = dt.datetime(2026, 8, 11, 18, 30, tzinfo=dt.UTC)
DAY_TWO = dt.datetime(2026, 8, 12, 18, 30, tzinfo=dt.UTC)

#: The two closes driven into Postgres, as (trade_id, exit_price, stamp). The
#: first is a LOSS and the second a WIN, so the advance has a sign to get wrong.
DRIVES: Final[tuple[tuple[str, float, dt.datetime], ...]] = (
    ("arc037a-T1", 4990.0, DAY_ONE),
    ("arc037a-T2", 5030.0, DAY_TWO),
)

#: Non-vacuity floors for the Postgres arm.
EXPECTED_LANDED: Final[int] = 4  # two closes × (protective_exit + closed)
MIN_FIGURES: Final[int] = 2

#: Float tolerance. The arms assert arithmetic identities, so this is for
#: representation and nothing else.
TOL: Final[float] = 1e-9

#: The tree the plants are driven against. Copied whole rather than file by
#: file: a partial copy that failed to import would report a BLIND control for a
#: reason that has nothing to do with the defect it carries.
_PLANT_TREE: Final[tuple[str, ...]] = ("scripts/nixrisk", "scripts/nixscore")
_PLANT_FILES: Final[tuple[str, ...]] = ("scripts/broker/broker_seam.py",)

_PACKAGES: Final[tuple[str, ...]] = ("nixrisk", "nixscore")


class Unmeasurable(Exception):
    """The subject could not be reached, so nothing was measured (§17)."""


class PlantFailed(Exception):
    """A plant's anchor was not found. The control is BLIND, never quietly green."""


@dataclasses.dataclass(frozen=True)
class Finding:  # pylint: disable=too-few-public-methods
    """One defect, anchored to the site that carries it and the reason (§18)."""

    site: str
    why: str


@dataclasses.dataclass(frozen=True)
class Mods:  # pylint: disable=too-few-public-methods,too-many-instance-attributes
    """The subject's modules, imported from one tree."""

    flatten: Any
    realized: Any
    seam: Any
    picture: Any
    reservations: Any
    plane1_sink: Any
    wal: Any
    ema: Any
    broker_seam: Any


# ---------------------------------------------------------------------------
# Loading — out of a named tree, never this process's own by accident
# ---------------------------------------------------------------------------


def _purge(saved: dict[str, types.ModuleType]) -> None:
    """Drop the subject packages from `sys.modules` and restore `saved`.

    Named packages only. `sys.modules.clear()` is what D3.270 was: it evicts C
    extension modules and hands unrelated gates an exception their own correct
    handler cannot catch.
    """
    for name in [
        key
        for key in list(sys.modules)
        if key in _PACKAGES or any(key.startswith(f"{pkg}.") for pkg in _PACKAGES)
    ]:
        del sys.modules[name]
    sys.modules.update(saved)


def load(home: Path) -> Mods:
    """Import the subject from `home`. Raises `Unmeasurable` (§17: never PASS)."""
    saved_path = list(sys.path)
    saved_modules = {
        key: value
        for key, value in sys.modules.items()
        if key in _PACKAGES or any(key.startswith(f"{pkg}.") for pkg in _PACKAGES)
    }
    _purge({})
    sys.path.insert(0, str((home / "scripts").resolve()))
    sys.path.insert(0, str((home / "scripts" / "broker").resolve()))
    importlib.invalidate_caches()
    try:
        return _resolved_in(
            home,
            Mods(
                flatten=importlib.import_module("nixrisk.flatten"),
                realized=importlib.import_module("nixrisk.realized"),
                seam=importlib.import_module("nixrisk.seam"),
                picture=importlib.import_module("nixrisk.picture"),
                reservations=importlib.import_module("nixrisk.reservations"),
                plane1_sink=importlib.import_module("nixrisk.plane1_sink"),
                wal=importlib.import_module("nixrisk.wal"),
                ema=importlib.import_module("nixscore.ema"),
                broker_seam=importlib.import_module("broker_seam"),
            ),
        )
    except Exception as exc:  # pylint: disable=broad-except
        raise Unmeasurable(
            f"cannot import the realized-P&L wire from {home} — "
            f"{type(exc).__name__}: {exc}. The subject is unavailable, so "
            "nothing was measured (§17: never a PASS)"
        ) from exc
    finally:
        sys.path[:] = saved_path
        _purge(saved_modules)


def _resolved_in(home: Path, mods: Mods) -> Mods:
    """The loaded modules, PROVEN to come from `home`. §17, and a measured trap.

    `sys.path` already carries a `scripts/` directory in every context this gate
    runs in — `_preamble` puts the real one there, and pytest's own conftest
    does too. Inserting `home/scripts` at position 0 therefore does NOT
    guarantee the import came from `home`: a tree with no `scripts/nixrisk` at
    all imports the REAL modules and every arm below then measures a subject the
    caller did not name. Measured on this gate's own suite before this guard
    existed: an empty `nix_home` loaded the shipped tree and got as far as
    reading its config.
    """
    outside = [
        f"{module.__name__} <- {module.__file__}"
        for module in (mods.flatten, mods.realized, mods.seam, mods.ema)
        if not str(Path(module.__file__ or "/dev/null").resolve()).startswith(
            str(home.resolve())
        )
    ]
    if outside:
        raise Unmeasurable(
            f"the realized-P&L wire asked for in {home} RESOLVED OUTSIDE IT: "
            f"{'; '.join(outside)}. sys.path already carried another tree, so "
            "every arm would have measured a subject the caller did not name "
            "(§17: never a PASS)"
        )
    return mods


def plant_tree(home: Path, tmp: Path, edits: tuple[tuple[str, str, str], ...]) -> Path:
    """A COPY of the subject tree with `edits` applied. Never the shipped file.

    `edits` are `(relative_path, anchor, replacement)`. A missing anchor raises
    `PlantFailed`: a `str.replace` that matched nothing leaves a PRISTINE
    subject, the arm finds no defect, and the arm's silence is then read as
    proof it can fail. That is the exact shape of a blind control (doctrine
    C.8 forbids planting on the production artifact).
    """
    root = tmp / f"plant-{uuid.uuid4().hex[:8]}"
    for rel in _PLANT_TREE:
        shutil.copytree(
            home / rel, root / rel, ignore=shutil.ignore_patterns("__pycache__")
        )
    for rel in _PLANT_FILES:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(home / rel, root / rel)
    for rel, anchor, replacement in edits:
        path = root / rel
        text = path.read_text(encoding="utf-8")
        if text.count(anchor) != 1:
            raise PlantFailed(
                f"plant anchor {anchor[:70]!r} appears {text.count(anchor)} "
                f"time(s) in {rel}, not once — the mutation did not apply, so "
                "the 'broken' subject is the shipped one and the control would "
                "be measuring nothing"
            )
        path.write_text(text.replace(anchor, replacement), encoding="utf-8")
    return root


# ---------------------------------------------------------------------------
# Doubles — hand-built, no pytest and no test-file import
# ---------------------------------------------------------------------------


class _Broker:
    """A `BrokerFlattenPort` whose flatten really removes the position."""

    def __init__(self, mods: Mods, positions: dict[str, int], cash: float) -> None:
        self._cls = mods.broker_seam.Position
        self._balance = mods.broker_seam.Balance
        self._positions = dict(positions)
        self._cash = cash
        self.flatten_calls: list[str | None] = []

    def flatten(self, symbol: str | None = None) -> None:
        """The §2A sync verb. Removes the position, as a real flatten does."""
        self.flatten_calls.append(symbol)
        for sym in [symbol] if symbol else list(self._positions):
            self._positions.pop(sym, None)

    def cancel_order(self, client_order_id: str) -> None:
        """Unused here; the port requires it."""
        del client_order_id

    async def query_positions(self) -> list[Any]:
        """Broker truth AFTER the flatten — what reconcile reads (§4)."""
        return [
            self._cls(symbol=sym, net_qty=qty, avg_price=5000.0)
            for sym, qty in self._positions.items()
        ]

    async def query_balance(self) -> Any:
        """Broker-authoritative balance on every reconciliation (§4)."""
        return self._balance(
            cash=self._cash,
            net_liquidation=self._cash,
            maint_margin=0.0,
            init_margin=0.0,
            venue_seq_ts=0.0,
        )


class _StrategySink:  # pylint: disable=too-few-public-methods
    def on_closed(
        self, trade_id: str, strategy_id: str, reason: str, *, hard_reset: bool
    ) -> None:
        """§4 fan-out (a). Not this gate's subject; recorded nowhere."""
        del trade_id, strategy_id, reason, hard_reset


class _ScoringSink:  # pylint: disable=too-few-public-methods
    """§4 fan-out (d). Records the ACCOUNT-LEVEL delta — the figure that cannot
    be keyed to a pair, and the reason this arc wrote a second path."""

    def __init__(self) -> None:
        self.booked: list[tuple[tuple[str, ...], float]] = []

    def book_realized(
        self,
        *,
        closed_trades: tuple[str, ...],
        realized_delta: float,
        confirmed_balance: float,
        ts: float,
    ) -> None:
        """Book the ACCOUNT delta — the figure that cannot be keyed to a pair."""
        del confirmed_balance, ts
        self.booked.append((closed_trades, realized_delta))


class _Recorder:
    """§9's port, in memory. The Postgres arm uses the REAL WAL instead."""

    def __init__(self) -> None:
        self.rows: list[Any] = []

    def enqueue(self, row: Any) -> None:
        """Append one row. Bounded and not durable, like the real WAL."""
        self.rows.append(row)

    def sync_to_disk(self) -> int:
        """No durability here; the Postgres arm uses the REAL WAL."""
        return 0

    def pending(self) -> int:
        """Rows enqueued. §12.4's disk-critical input, unused in this gate."""
        return len(self.rows)


# ---------------------------------------------------------------------------
# The drive
# ---------------------------------------------------------------------------


def _facts(  # pylint: disable=too-many-arguments
    mods: Mods,
    *,
    trade_id: str,
    symbol: str = SYMBOL,
    strategy_id: str = STRATEGY,
    entry_price: float = 5000.0,
    exit_price: float,
    peak_price: float | None = None,
    qty: int = 2,
    point_value: float = 5.0,
) -> Any:
    """One closed round trip's facts, with the modelled §6.5/§7 costs."""
    realized = mods.realized
    return realized.TradeFacts(
        entry=realized.TradeEntry(
            trade_id=trade_id,
            strategy_id=strategy_id,
            symbol=symbol,
            side=mods.seam.Side.LONG,
            qty=qty,
            price=entry_price,
            point_value=point_value,
            commission=0.62,
        ),
        exit=realized.TradeExit(
            trade_id=trade_id,
            price=exit_price,
            commission=0.62,
            fees=0.14,
            slippage_cost=2.5,
        ),
        peak_price=peak_price,
    )


def _position_row(mods: Mods, trade_id: str, symbol: str, strategy_id: str) -> Any:
    return mods.seam.PositionRow(
        trade_id=trade_id,
        symbol=symbol,
        strategy_id=strategy_id,
        size=2,
        margin=1000.0,
        state=mods.seam.PositionState.OPEN,
        stop_distance=20,
    )


def _executor(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    mods: Mods,
    broker: Any,
    port: Any,
    book: Any,
    rows: list[Any],
    ts: float,
) -> Any:
    """One `ProtectiveFlatten` over a mirror holding `rows`, booking into `port`."""
    picture = mods.picture.FinancialPictureBook(
        balance=20344.34, deployable_fraction=0.70, sink=None
    )
    picture.commit(balance=20344.34, positions=list(rows))
    return mods.flatten.ProtectiveFlatten(
        broker=broker,
        ledger=mods.reservations.ReservationLedger(port),
        picture=picture,
        strategy=_StrategySink(),
        plane1=port,
        scoring=_ScoringSink(),
        trade_facts=book,
        clock=lambda: ts,
    )


async def drive_close(  # pylint: disable=too-many-arguments
    mods: Mods,
    port: Any,
    *,
    trade_id: str,
    exit_price: float,
    stamp: dt.datetime,
    peak_price: float | None = None,
    facts_known_early: bool = False,
) -> Any:
    """One REAL protective close, reconciled, booking onto `port`.

    The facts are recorded AFTER `request_close` and BEFORE reconcile, which is
    the real sequence: at protective-exit time no exit fill is confirmed (§4 —
    *"we sent a flatten"* and *"the position is confirmed flat"* are different
    facts), so the book cannot answer yet. `facts_known_early` drives the other
    ordering, which is what a §12.1 marker replay looks like.
    """
    book = mods.realized.RecordedTradeFacts()
    facts = _facts(
        mods, trade_id=trade_id, exit_price=exit_price, peak_price=peak_price
    )
    if facts_known_early:
        book.record(facts)
    broker = _Broker(mods, {SYMBOL: 2}, 20344.34)
    executor = _executor(
        mods,
        broker,
        port,
        book,
        [_position_row(mods, trade_id, SYMBOL, STRATEGY)],
        stamp.timestamp(),
    )
    executor.request_close(
        mods.flatten.CloseTarget(
            trade_id=trade_id, symbol=SYMBOL, strategy_id=STRATEGY
        ),
        mods.flatten.CloseAuthority.PROTECTIVE,
        "synthetic stop",
    )
    if not facts_known_early:
        book.record(facts)
    return await executor.reconcile_and_publish()


def run_drive(coroutine: Any) -> Any:
    """Drive one coroutine to completion without pytest-asyncio."""
    import asyncio  # pylint: disable=import-outside-toplevel

    return asyncio.run(coroutine)


def realizing_rows(mods: Mods, rows: list[Any]) -> tuple[list[Any], list[Any]]:
    """Realizing-typed rows split into figure-carrying and reason-carrying.

    NO REALIZING ROW MAY BE SILENT. `ema.realized_closes` refuses a realizing
    row with no figure, and `flatten` books TWO realizing-typed rows for one
    protective close of which exactly one may carry a number (§6.6:438's per-day
    reduction SUMS them). So the split is asserted TOTAL by the caller and only
    the figure-carrying half is folded.
    """
    resolve = mods.plane1_sink.resolve_event_type
    realizing = [
        row for row in rows if resolve(row.kind) in mods.ema.REALIZING_EVENT_TYPES
    ]
    figures = [row for row in realizing if mods.realized.REALIZED_FIELD in row.fields]
    reasons = [row for row in realizing if mods.realized.STATUS_FIELD in row.fields]
    return figures, reasons


def figure_of(mods: Mods, row: Any) -> float:
    """One row's written realized figure, read back through `float`."""
    return float(row.fields[mods.realized.REALIZED_FIELD])


# ---------------------------------------------------------------------------
# ARM: the wire, END TO END, through real Postgres
# ---------------------------------------------------------------------------


def _psql(database: str, sql: str) -> str:
    binary = shutil.which("psql")
    if binary is None:
        raise Unmeasurable("psql is not on PATH — the Plane-1 transport is absent")
    proc = subprocess.run(  # nosec B603 - fixed argv, no shell
        [binary, "-d", database, "-qAt", "-v", "ON_ERROR_STOP=1", "-c", sql],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if proc.returncode != 0:
        raise Unmeasurable(f"{database}: {proc.stderr.strip()[-300:]}")
    return proc.stdout.strip()


def scratch_database(home: Path) -> str:
    """A scratch Plane-1 database built by the shipped provisioner from the
    shipped DDL — never a hand-written table, which would let this gate pass
    against a schema production does not have."""
    if shutil.which("psql") is None or shutil.which("createdb") is None:
        raise Unmeasurable("psql/createdb are not on PATH")
    sys.path.insert(0, str((home / "scripts").resolve()))
    try:
        import provision_plane1  # pylint: disable=import-outside-toplevel
    except ImportError as exc:
        raise Unmeasurable(f"cannot import provision_plane1: {exc!r}") from exc
    name = provision_plane1.SCRATCH_PREFIX + "realized_" + uuid.uuid4().hex[:10]
    try:
        outcome, detail = provision_plane1.provision(name, provision_plane1.SCHEMA_SQL)
    except provision_plane1.ProvisionError as exc:
        raise Unmeasurable(f"cannot build a scratch Plane-1 database: {exc}") from exc
    if outcome != "created":
        raise Unmeasurable(f"provisioning {name} returned {outcome}: {detail}")
    return name


def drop_database(name: str) -> None:
    """Drop the scratch database. Best effort: a leaked scratch db is noise, and
    raising here would turn cleanup into the gate's verdict."""
    binary = shutil.which("dropdb")
    if binary is None or not name:
        return
    subprocess.run(  # nosec B603 - fixed argv, no shell
        [binary, "--if-exists", "--force", name],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def read_back(database: str) -> list[dict[str, Any]]:
    """Every row this gate wrote, READ OUT OF POSTGRES as `ema` reads them.

    The SQL is the instrument. The returned mappings are built from what the
    DATABASE returned — `payload` is parsed from the JSONB text, `occurred_at`
    from the timestamp — so nothing the writer still holds in memory can reach
    the fold.
    """
    out = _psql(
        database,
        "select event_id::text, event_type::text, strategy_id, trade_id, "
        "coalesce(symbol, ''), to_char(occurred_at at time zone 'UTC', "
        "'YYYY-MM-DD\"T\"HH24:MI:SSOF'), payload::text "
        f"from plane1_event_log where strategy_id = '{STRATEGY}' "  # nosec B608
        "order by wal_seq",
    )
    rows: list[dict[str, Any]] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("|", 6)
        rows.append(
            {
                "event_id": parts[0],
                "event_type": parts[1],
                "strategy_id": parts[2],
                "trade_id": parts[3],
                "symbol": parts[4] or None,
                "occurred_at": parts[5],
                "payload": json.loads(parts[6]),
            }
        )
    return rows


def _commit_all(mods: Mods, wal: Any, sink: Any, attempts: int) -> None:
    """Group-commit the WAL to exhaustion through the real seam."""
    writer = mods.wal.GroupCommitWriter(wal, sink, batch_max=8)
    for _ in range(attempts):
        result = writer.drain_once()
        if result.error:
            raise Unmeasurable(f"group-commit FAILED: {result.error[-300:]}")
        if result.backlog == 0:
            return


def _arm_wire(  # pylint: disable=too-many-locals
    mods: Mods, database: str, tmp: Path, span: int
) -> tuple[list[Finding], str]:
    """THE KEYSTONE. Write two real closes, read them back by SQL, and require
    the EMA to advance off the DATABASE's own rows."""
    findings: list[Finding] = []
    wal_path = tmp / f"realized-{uuid.uuid4().hex[:8]}.wal"
    wal = mods.wal.Plane1Wal(wal_path)
    try:
        for trade_id, exit_price, stamp in DRIVES:
            run_drive(
                drive_close(
                    mods, wal, trade_id=trade_id, exit_price=exit_price, stamp=stamp
                )
            )
        wal.sync_to_disk()
        _commit_all(mods, wal, mods.plane1_sink.Plane1PostgresSink(database), 12)
    finally:
        wal.close()
        wal_path.unlink(missing_ok=True)

    rows = read_back(database)
    if len(rows) != EXPECTED_LANDED:
        return (
            [
                Finding(
                    f"{NAME}:non-vacuity",
                    f"{len(rows)} row(s) read back out of {database}, not the "
                    f"{EXPECTED_LANDED} this arm drove — the fold below would be "
                    "over a population that is not what was written",
                )
            ],
            "",
        )
    carried = [row for row in rows if mods.realized.REALIZED_FIELD in row["payload"]]
    if len(carried) < MIN_FIGURES:
        findings.append(
            Finding(
                f"{FLATTEN_FILE}:_realizing_fields",
                f"only {len(carried)} of {len(rows)} landed row(s) carry "
                f"{mods.realized.REALIZED_FIELD!r} in their payload. §6.6 reads "
                "the figure out of the durable record, so a realization the "
                "record does not carry cannot be scored at all",
            )
        )
        return findings, ""

    closes = mods.ema.realized_closes(carried)
    scored = mods.ema.score_pairs(closes, span, DAY_TWO.date())
    key = (STRATEGY, SYMBOL)
    if key not in scored:
        findings.append(
            Finding(
                f"{EMA_FILE}:score_pairs",
                f"the fold produced no row for {key} — §6.6:448 locks "
                "(strategy_id, symbol) as the canonical key and the written rows "
                f"scored {sorted(scored)} instead",
            )
        )
        return findings, ""

    first = mods.ema.score_pairs(closes[:1], span, DAY_ONE.date())[key].realized_ema
    after = scored[key].realized_ema
    values = [close.realized for close in closes]
    alpha = mods.ema.alpha_for(span)
    expected = values[0] + alpha * (values[1] - values[0])
    if abs(after - expected) > TOL:
        findings.append(
            Finding(
                f"{EMA_FILE}:ema_over_days",
                f"the EMA over the two rows the DATABASE returned is {after!r}, "
                f"not the closed form v1 + alpha*(v2-v1) = {expected!r} at span "
                f"{span} (alpha={alpha!r}) over values {values}",
            )
        )
    if abs(after - first) <= TOL:
        findings.append(
            Finding(
                f"{EMA_FILE}:ema_over_days",
                f"the EMA did NOT advance: {first!r} before the second written "
                f"row and {after!r} after it. A score that does not move when a "
                "realization lands is a score nothing is feeding — which is "
                "D3.220 exactly, and is what this gate exists to detect",
            )
        )
    evidence = (
        f"wrote {len(rows)} realizing row(s) into {database} through "
        f"Plane1Wal -> GroupCommitWriter -> Plane1PostgresSink; read back by "
        f"SELECT; {len(carried)} carried "
        f"{mods.realized.REALIZED_FIELD} = {values}; EMA at span {span} advanced "
        f"{first!r} -> {after!r} (closed form {expected!r}, tol {TOL})"
    )
    return findings, evidence


# ---------------------------------------------------------------------------
# ARM: the figure is the CLOSE, never the PEAK
# ---------------------------------------------------------------------------


def peak_defects(mods: Mods) -> list[Finding]:
    """§6.6:435 — a position GREEN WHILE OPEN that CLOSES RED realizes the RED."""
    port = _Recorder()
    run_drive(
        drive_close(
            mods,
            port,
            trade_id="arc037a-peak",
            exit_price=4990.0,
            peak_price=5015.0,
            stamp=DAY_TWO,
        )
    )
    figures, _ = realizing_rows(mods, port.rows)
    if len(figures) != 1:
        return [
            Finding(
                f"{FLATTEN_FILE}:_realizing_fields",
                f"{len(figures)} row(s) carried a figure for one close, not 1 — "
                "the peak arm had nothing to judge",
            )
        ]
    written = figure_of(mods, figures[0])
    findings: list[Finding] = []
    if written >= 0.0:
        findings.append(
            Finding(
                f"{REALIZED_FILE}:realized_pnl",
                f"the written figure is {written!r} for a trade that entered at "
                "5000.0, PEAKED at 5015.0 while open and CLOSED at 4990.0. "
                "§6.6:435: 'Realized P&L only — closed trades. Unrealized/paper "
                "gains never steer capital (a green open position can reverse "
                "before it closes)'",
            )
        )
    if abs(written - (-103.88)) > 1e-6:
        findings.append(
            Finding(
                f"{REALIZED_FILE}:realized_pnl",
                f"the written figure is {written!r}; the CLOSE-derived figure is "
                "-103.88 (gross -100.00 less 3.88 of commissions, fees and "
                "slippage, §6.5:409-410 / §7:481) and the PEAK-derived one is "
                "+146.12. The figure must be the first",
            )
        )
    return findings


# ---------------------------------------------------------------------------
# ARM: exactly ONE figure per closed trade, and no realizing row is SILENT
# ---------------------------------------------------------------------------


def once_defects(mods: Mods) -> list[Finding]:
    """`ema.daily_advances` SUMS a pair's realizing rows for the day.

    **BOTH ORDERINGS ARE DRIVEN, and that is what makes the arm able to fail.**
    In the ordinary sequence the facts arrive between the protective exit and
    the reconcile, so the first realizing row has nothing to price and only the
    `closed` row can carry a figure — the once-only ledger is never consulted
    and its removal changes nothing. Measured, not reasoned: the
    `double-counting-writer` plant produced NO finding against that ordering.
    The §12.1 marker-replay ordering — facts already known when the exit fires —
    is the one where TWO rows can each price the same close, and it is the one
    the plant must be judged against.
    """
    findings = _once_in_one_ordering(mods, "arc037a-once", early=False)
    findings += _once_in_one_ordering(mods, "arc037a-once-early", early=True)
    return findings


def _once_in_one_ordering(mods: Mods, trade_id: str, *, early: bool) -> list[Finding]:
    """One close, one ordering: exactly ONE figure, and it is the trade's own."""
    port = _Recorder()
    run_drive(
        drive_close(
            mods,
            port,
            trade_id=trade_id,
            exit_price=4990.0,
            stamp=DAY_TWO,
            facts_known_early=early,
        )
    )
    figures, reasons = realizing_rows(mods, port.rows)
    where = (
        "facts known at the exit (§12.1 replay)" if early else "facts after reconcile"
    )
    total = sum(figure_of(mods, row) for row in figures)
    if len(figures) == 1 and abs(total - (-103.88)) > 1e-6:
        return [
            Finding(
                f"{FLATTEN_FILE}:_realizing_fields",
                f"{where}: the one figure written is {total!r}, not the trade's "
                "own -103.88",
            )
        ]
    if len(figures) != 1:
        return [
            Finding(
                f"{FLATTEN_FILE}:_realized_booked",
                f"{where}: {len(figures)} realizing row(s) carry a figure for ONE "
                f"closed trade, summing to {total!r} against the trade's own "
                "-103.88. §6.6:438 reduces a pair's day by SUMMING its "
                "realizations, so a second row carrying the same close doubles "
                "its contribution to the rank",
            )
        ]
    return _once_shape_defects(mods, figures, reasons, port.rows, where)


def _once_shape_defects(  # pylint: disable=too-many-arguments
    mods: Mods,
    figures: list[Any],
    reasons: list[Any],
    rows: list[Any],
    where: str,
) -> list[Finding]:
    """The partition is TOTAL and every deferral NAMES its reason (rule 11)."""
    port = _Recorder()
    port.rows = rows
    del port
    resolve = mods.plane1_sink.resolve_event_type
    realizing = [
        row for row in rows if resolve(row.kind) in mods.ema.REALIZING_EVENT_TYPES
    ]
    findings: list[Finding] = []
    if len(realizing) < 2:
        findings.append(
            Finding(
                f"{NAME}:once-non-vacuity",
                f"{where}: {len(realizing)} realizing row(s) were booked for one "
                "protective close, so the once-only property was judged over a "
                "population that cannot express it",
            )
        )
    if len(figures) + len(reasons) != len(realizing):
        findings.append(
            Finding(
                f"{FLATTEN_FILE}:_realizing_fields",
                f"{where}: {len(realizing) - len(figures) - len(reasons)} "
                "realizing row(s) carry NEITHER a figure NOR a named reason. A "
                "silent realizing "
                "row is refused by `ema.realized_closes` with no way to tell a "
                "deferral from a defect",
            )
        )
    for row in reasons:
        text = row.fields[mods.realized.STATUS_FIELD]
        if len(text) < 20 or mods.realized.REALIZED_FIELD in row.fields:
            findings.append(
                Finding(
                    f"{FLATTEN_FILE}:_realized_or_reason",
                    f"the deferring {row.kind.value!r} row's reason is {text!r} — "
                    "check contract rule 11: a control asserts the REASON, and a "
                    "row that says a figure is absent must say WHY",
                )
            )
    return findings


# ---------------------------------------------------------------------------
# ARM: no unrealized mark on a realizing row
# ---------------------------------------------------------------------------


def banned_defects(mods: Mods, rows: list[dict[str, Any]]) -> list[Finding]:
    """§6.6:435's field-name door, judged on the payloads POSTGRES returned."""
    findings: list[Finding] = []
    for row in rows:
        if row["event_type"] not in mods.ema.REALIZING_EVENT_TYPES:
            continue
        leaked = sorted(mods.ema.BANNED_UNREALIZED_FIELDS & set(row["payload"]))
        if leaked:
            findings.append(
                Finding(
                    f"{FLATTEN_FILE}:_realizing_fields",
                    f"the landed {row['event_type']} row for trade "
                    f"{row['trade_id']} carries {', '.join(leaked)} beside its "
                    "realization. §6.6:435 forbids a mark steering capital, and "
                    "a payload carrying both figures is one field name away from "
                    "steering on the wrong one",
                )
            )
    if not rows:
        findings.append(
            Finding(
                f"{NAME}:banned-non-vacuity",
                "no landed row was inspected for a mark, so the ban was judged "
                "over nothing",
            )
        )
    return findings


# ---------------------------------------------------------------------------
# ARM: the writer's key IS the key the reader reads
# ---------------------------------------------------------------------------


def constant_defects(mods: Mods) -> list[Finding]:
    """The writer restates the scorer's constants (the exit path must not import
    the ranking optimisation). The restatement is held equal MECHANICALLY."""
    findings: list[Finding] = []
    if mods.realized.REALIZED_FIELD != mods.ema.REALIZED_FIELD:
        findings.append(
            Finding(
                f"{REALIZED_FILE}:REALIZED_FIELD",
                f"the writer writes {mods.realized.REALIZED_FIELD!r} and the "
                f"scorer reads {mods.ema.REALIZED_FIELD!r} — the wire is parted, "
                "and every row would land in a payload nothing reads",
            )
        )
    if mods.realized.BANNED_UNREALIZED_FIELDS != mods.ema.BANNED_UNREALIZED_FIELDS:
        only_writer = sorted(
            mods.realized.BANNED_UNREALIZED_FIELDS - mods.ema.BANNED_UNREALIZED_FIELDS
        )
        only_reader = sorted(
            mods.ema.BANNED_UNREALIZED_FIELDS - mods.realized.BANNED_UNREALIZED_FIELDS
        )
        findings.append(
            Finding(
                f"{REALIZED_FILE}:BANNED_UNREALIZED_FIELDS",
                f"the writer's ban and the scorer's disagree: writer-only "
                f"{only_writer}, reader-only {only_reader}. A name the reader "
                "bans and the writer does not is a mark that reaches the record",
            )
        )
    written = {
        mods.plane1_sink.EVENT_KIND_TO_PLANE1[mods.seam.EventKind.CLOSED],
        mods.plane1_sink.EVENT_KIND_TO_PLANE1[mods.seam.EventKind.PROTECTIVE_EXIT],
    }
    if not written <= mods.ema.REALIZING_EVENT_TYPES:
        findings.append(
            Finding(
                f"{FLATTEN_FILE}:_book",
                f"the writer marks {sorted(written - mods.ema.REALIZING_EVENT_TYPES)} "
                "realizing and the scorer does not classify them as realizations "
                "— those rows would be refused as unrealized leaks",
            )
        )
    return findings


# ---------------------------------------------------------------------------
# ARM: the figure is PER PAIR, not the account delta
# ---------------------------------------------------------------------------


def attribution_defects(mods: Mods) -> list[Finding]:
    """§6.6:448. Two trades close in ONE reconcile; the account delta is their
    SUM and is attributable to neither pair."""
    port = _Recorder()
    book = mods.realized.RecordedTradeFacts()
    broker = _Broker(mods, {SYMBOL: 2, "MNQU6": 2}, 20344.34)
    scoring = _ScoringSink()
    picture = mods.picture.FinancialPictureBook(
        balance=20344.34, deployable_fraction=0.70, sink=None
    )
    picture.commit(
        balance=20344.34,
        positions=[
            _position_row(mods, "arc037a-A", SYMBOL, STRATEGY),
            _position_row(mods, "arc037a-B", "MNQU6", f"{STRATEGY}_2"),
        ],
    )
    executor = mods.flatten.ProtectiveFlatten(
        broker=broker,
        ledger=mods.reservations.ReservationLedger(port),
        picture=picture,
        strategy=_StrategySink(),
        plane1=port,
        scoring=scoring,
        trade_facts=book,
        clock=DAY_TWO.timestamp,
    )
    executor.fire(
        mods.seam.FlattenTrigger.NET_LIQ_FLOOR,
        targets=[
            mods.flatten.CloseTarget(
                trade_id="arc037a-A", symbol=SYMBOL, strategy_id=STRATEGY
            ),
            mods.flatten.CloseTarget(
                trade_id="arc037a-B", symbol="MNQU6", strategy_id=f"{STRATEGY}_2"
            ),
        ],
    )
    book.record(_facts(mods, trade_id="arc037a-A", exit_price=4990.0))
    book.record(
        _facts(
            mods,
            trade_id="arc037a-B",
            symbol="MNQU6",
            strategy_id=f"{STRATEGY}_2",
            exit_price=5030.0,
            point_value=2.0,
        )
    )
    run_drive(executor.reconcile_and_publish())

    figures, _ = realizing_rows(mods, port.rows)
    values = {
        row.fields[mods.realized.SYMBOL_FIELD]: figure_of(mods, row) for row in figures
    }
    findings: list[Finding] = []
    if len(values) != 2:
        findings.append(
            Finding(
                f"{FLATTEN_FILE}:_fan_out",
                f"two trades closed in one reconcile and {len(values)} attributed "
                f"figure(s) were written ({values}). §6.6:448 keys the row on the "
                "PAIR, so one number for two pairs cannot be scored",
            )
        )
        return findings
    delta = scoring.booked[0][1] if scoring.booked else 0.0
    for symbol, value in values.items():
        if abs(value - delta) <= TOL:
            findings.append(
                Finding(
                    f"{FLATTEN_FILE}:_realizing_fields",
                    f"the figure written for {symbol} is {value!r}, which is the "
                    f"ACCOUNT-LEVEL delta {delta!r} that ScoringSink."
                    "book_realized carries for BOTH closes. That number cannot "
                    "be attributed to one pair (§6.6:448) and reusing it is the "
                    "defect D3.220 names",
                )
            )
    if len(set(values.values())) != 2:
        findings.append(
            Finding(
                f"{FLATTEN_FILE}:_realizing_fields",
                f"both pairs were written the SAME figure {values} — two "
                "different trades on two different symbols cannot have realized "
                "the same amount here, so the figure is not per-trade",
            )
        )
    return findings


# ---------------------------------------------------------------------------
# THE CAN-FAIL CONTROLS — each plant must flip the arm it guards
# ---------------------------------------------------------------------------

#: `(label, edits, predicate)` — the predicate reports whether the PLANTED tree
#: is caught. Each anchor is a real line of the shipped source.
_PEAK_ANCHOR = "    figure: RealizedPnl = realized_pnl(facts.entry, facts.exit)\n"
_PEAK_PLANT = (
    "    figure: RealizedPnl = realized_pnl(\n"
    "        facts.entry,\n"
    "        facts.exit\n"
    "        if facts.peak_price is None\n"
    "        else TradeExit(\n"
    "            trade_id=facts.exit.trade_id,\n"
    "            price=facts.peak_price,\n"
    "            commission=facts.exit.commission,\n"
    "            fees=facts.exit.fees,\n"
    "            slippage_cost=facts.exit.slippage_cost,\n"
    "        ),\n"
    "    )\n"
)

_ONCE_ANCHOR = "        booked = self._realized_booked.get(trade_id)\n"
_ONCE_PLANT = "        booked = None\n"

_BANNED_ANCHOR = (
    "        self._realized_booked[str(trade_id)] = kind.value\n"
    "        return outcome\n"
)
_BANNED_PLANT = (
    "        self._realized_booked[str(trade_id)] = kind.value\n"
    '        outcome["unrealized_pnl"] = "12.5"\n'
    "        return outcome\n"
)

_MISSING_ANCHOR = "                realizing=True,\n"
_MISSING_PLANT = "                realizing=False,\n"

PLANTS: Final[tuple[tuple[str, tuple[tuple[str, str, str], ...]], ...]] = (
    ("peak-priced-writer", ((REALIZED_FILE, _PEAK_ANCHOR, _PEAK_PLANT),)),
    ("double-counting-writer", ((FLATTEN_FILE, _ONCE_ANCHOR, _ONCE_PLANT),)),
    ("banned-field-writer", ((FLATTEN_FILE, _BANNED_ANCHOR, _BANNED_PLANT),)),
    ("figure-stripped-writer", ((FLATTEN_FILE, _MISSING_ANCHOR, _MISSING_PLANT),)),
)


def _planted_defects(label: str, mods: Mods) -> list[Finding]:
    """The arm each plant is supposed to trip, driven on the PLANTED tree."""
    if label == "peak-priced-writer":
        return peak_defects(mods)
    if label == "double-counting-writer":
        return once_defects(mods)
    if label == "banned-field-writer":
        return _banned_on_written_rows(mods)
    return _missing_on_written_rows(mods)


def _written_payloads(mods: Mods) -> list[dict[str, Any]]:
    """One driven close's rows in the shape `ema` reads, without Postgres.

    The Postgres arm is the one that proves the transport; this shape exists so
    the PLANTS can be driven without building four scratch databases.
    """
    port = _Recorder()
    run_drive(
        drive_close(
            mods, port, trade_id="arc037a-plant", exit_price=4990.0, stamp=DAY_TWO
        )
    )
    resolve = mods.plane1_sink.resolve_event_type
    return [
        {
            "event_id": f"{row.kind.value}-{row.trade_id}",
            "event_type": resolve(row.kind),
            "strategy_id": row.strategy_id,
            "trade_id": row.trade_id,
            "symbol": row.fields.get(mods.realized.SYMBOL_FIELD),
            "occurred_at": DAY_TWO,
            "payload": {**dict(row.fields), "event_kind": row.kind.value},
        }
        for row in port.rows
    ]


def _banned_on_written_rows(mods: Mods) -> list[Finding]:
    return banned_defects(mods, _written_payloads(mods))


def _missing_on_written_rows(mods: Mods) -> list[Finding]:
    """The negative: strip the figure and require `MissingRealized` BY NAME.

    Driven two ways, because they answer different questions. First the row the
    writer produced is checked for the key at all; then the key is REMOVED from
    a row that had one and the scorer's own refusal is required to fire and to
    name it — which is what proves the reader is reading THIS key rather than
    tolerating its absence.
    """
    rows = _written_payloads(mods)
    realizing = [
        row for row in rows if row["event_type"] in mods.ema.REALIZING_EVENT_TYPES
    ]
    carried = [
        row for row in realizing if mods.realized.REALIZED_FIELD in row["payload"]
    ]
    findings: list[Finding] = []
    if not carried:
        findings.append(
            Finding(
                f"{FLATTEN_FILE}:_book",
                f"no realizing row of {len(realizing)} carries "
                f"{mods.realized.REALIZED_FIELD!r}. §6.6 reads the figure out of "
                "the durable record; a close the record does not price cannot be "
                "scored, and a scorer with no input is indistinguishable from a "
                "healthy cold start",
            )
        )
        return findings
    stripped = dict(carried[0])
    stripped["payload"] = {
        key: value
        for key, value in carried[0]["payload"].items()
        if key != mods.realized.REALIZED_FIELD
    }
    try:
        mods.ema.realized_closes([stripped])
    except mods.ema.MissingRealized as exc:
        if mods.realized.REALIZED_FIELD not in str(exc):
            findings.append(
                Finding(
                    f"{EMA_FILE}:_realized_amount",
                    f"the refusal does not name the key: {str(exc)[:160]!r} "
                    "(check contract rule 11 — a control asserts the REASON)",
                )
            )
        return findings
    findings.append(
        Finding(
            f"{EMA_FILE}:realized_closes",
            "a realizing row with NO realized figure was folded without a "
            "refusal. `MissingRealized` is the only thing keeping an absent "
            "figure from being read as a zero advance, which would score every "
            "pair 0.0 and make a blind engine look like a cold start",
        )
    )
    return findings


def controls(home: Path, tmp: Path) -> tuple[str, str]:
    """Drive every plant. Returns `(blind_label, why)` — `('', '')` when all of
    them were caught."""
    for label, edits in PLANTS:
        try:
            root = plant_tree(home, tmp, edits)
            mods = load(root)
        except (PlantFailed, Unmeasurable) as exc:
            return label, str(exc)
        try:
            found = _planted_defects(label, mods)
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            # A plant that makes the subject RAISE is still caught — the defect
            # was detected — but the reason is carried so a gate bug is
            # distinguishable from a detection (§18).
            found = [Finding(f"{NAME}:{label}", f"raised {type(exc).__name__}: {exc}")]
        if not found:
            return label, (
                f"the {label} plant produced NO finding. The arm it guards "
                "cannot fail, so its green says nothing about the shipped tree"
            )
    return "", ""


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def _drive_arm(label: str, arm: Any) -> list[Finding]:
    """One arm, with a raise turned into a finding rather than a crash."""
    try:
        return arm()
    except Unmeasurable:
        raise
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return [
            Finding(
                f"{NAME}:{label}",
                f"raised {type(exc).__name__} while being driven: {str(exc)[:200]}",
            )
        ]


def _measure(home: Path, tmp: Path) -> tuple[list[Finding], str, str, str]:
    """Every arm and every control. Returns (findings, evidence, blind, why)."""
    mods = load(home)
    span = mods.ema.span_days_from_config(home)
    database = scratch_database(home)
    try:
        findings, wire_evidence = _arm_wire(mods, database, tmp, span)
        landed = read_back(database)
    finally:
        drop_database(database)
    findings += _drive_arm("peak", lambda: peak_defects(mods))
    findings += _drive_arm("once", lambda: once_defects(mods))
    findings += _drive_arm("banned", lambda: banned_defects(mods, landed))
    findings += _drive_arm("constants", lambda: constant_defects(mods))
    findings += _drive_arm("attribution", lambda: attribution_defects(mods))
    findings += _drive_arm("missing", lambda: _missing_on_written_rows(mods))
    blind, why = controls(home, tmp)
    evidence = (
        f"{REALIZED_FILE} + {FLATTEN_FILE}'s realizing rows, DRIVEN: "
        f"{wire_evidence or 'the end-to-end wire arm reported a defect'}; "
        f"drove green-while-open -> closes-red (peak 5015.0, close 4990.0) and "
        f"required the CLOSE; required exactly one figure per closed trade over "
        f"{len(landed)} landed row(s); required no "
        f"{len(mods.ema.BANNED_UNREALIZED_FIELDS)} banned mark field on any "
        f"realizing payload; compared the writer's key and ban against "
        f"{EMA_FILE}'s in both directions; closed two trades in one reconcile "
        f"and required two figures neither equal to the account delta; and "
        f"drove {len(PLANTS)} plants, each required to trip the arm it guards"
    )
    return findings, evidence, blind, why


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Measure it. See the module docstring for what and why."""
    try:
        with tempfile.TemporaryDirectory(prefix="check-realized-") as raw:
            findings, evidence, blind, why = _measure(ctx.nix_home, Path(raw))
        if findings:
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site="; ".join(sorted({f.site for f in findings})),
                evidence=evidence
                + (f"; the {blind} control is BLIND: {why}" if blind else ""),
                detail="; ".join(f"{f.site}: {f.why}" for f in findings),
            )
        if blind:
            return CheckResult(
                name=NAME,
                status=Status.CANNOT_MEASURE,
                site=f"{NAME}:{blind}",
                detail=f"the {blind} control could not fail: {why}",
            )
        return CheckResult(name=NAME, status=Status.PASS, evidence=evidence)
    except Unmeasurable as exc:
        return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=str(exc))
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"gate raised {type(exc).__name__}: {exc}",
        )


# pylint: disable=duplicate-code
if __name__ == "__main__":
    from nixverify.actuation import standalone_main

    sys.exit(standalone_main(Path(__file__).resolve(), run, NAME))
