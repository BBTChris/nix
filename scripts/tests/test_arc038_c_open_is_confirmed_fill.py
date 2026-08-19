"""ARC 038 / sub-agent C — §14:970: *"'Open' = **confirmed fill** only. Never optimistic."*

Subject: the Limiter's whole ENTRY seam — `scripts/nixrisk/fills.py`,
`scripts/nixrisk/positions.py`, `scripts/nixrisk/execution.py` — read through every
surface a consumer could mistake for "open": §3's position table, §3's
`sum_open_margin` / `sum_reservations` / `committed`, the reservation ledger, the
synthetic stop book, the execution ledger, §9's Plane-1 WAL, and §12.7's ALLOCATOR
MIRROR over a REAL `ipc://` socket.

Authority: `docs/nics_risk_subsystem_spec_v1.3.md` §14:970, §14:968 (*"Every
uncertainty resolves toward **flat**"*), §3:159-164 (the published row and the
ATOMICITY rule), §15's C1 (*committed = open margin + PENDING reservations*) and
§15:1006's *"idempotent exec-report dedup"*.

WHAT WOULD HAVE TO BE TRUE FOR THIS SUITE TO MEASURE NOTHING (§7.12)
====================================================================
1. **The ack half would have to be checkable without the fill half.** It is not:
   "no surface reads open" is satisfied trivially by a rig that is simply broken.
   So every ack assertion is PAIRED with the same reading taken after a real fill
   on the SAME rig, and the fill half must MOVE it. That is ARC 035's lesson
   applied to a positive invariant: the half that must show something comes second,
   and the half that must show nothing comes first.
2. **The Allocator's view would have to be a local object.** A `PictureMirror`
   built over an in-process fake proves nothing about what crosses §12.7's wire, so
   the mirror here is a real `StateSubscriber` on a real `ipc://` endpoint fed by a
   real `StatePublisher`, and the fixture asserts the subscription was SEEN before
   any reading is trusted.
3. **The re-delivery would have to carry a new `exec_id`.** `check_fill_handler`'s
   only re-delivery is `_LATE_FILL = ("CO-1","e2",1,4)` — a new execution, i.e. a
   later fill. That cannot see ARC 038's finding FC3, which is about the SAME
   execution arriving twice. The arm here re-sends the byte-identical §2A event.

Every control asserts a MESSAGE, a SITE or a FIELD, never an exit code alone
(check contract rule 11). Every socket and publisher is closed in a fixture
finalizer; nothing here opens a `/dev/shm` segment.
"""
# pylint: disable=invalid-name,redefined-outer-name,protected-access
# pylint: disable=missing-function-docstring,too-few-public-methods
# Test names SHOUT the property; the sys.path bootstrap is identical in every suite.

from __future__ import annotations

import contextlib
import subprocess  # nosec B404 - `grep` is the enumeration instrument, see below
import sys
import time
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from nixbus import statebus  # pylint: disable=wrong-import-position
from nixrisk.degraded import Plane1Enqueuer  # pylint: disable=wrong-import-position
from nixrisk.execution import (  # pylint: disable=wrong-import-position
    ContradictoryExecution,
    ExecutionLedger,
    ExecutionReport,
    FillSide,
    IngestDisposition,
    InvalidExecutionReport,
)
from nixrisk.fills import (  # pylint: disable=wrong-import-position
    ApprovedOrderBook,
    FillHandler,
    IocRemainder,
    LimiterFillSink,
    UnapprovedFill,
)
from nixrisk.picture import (  # pylint: disable=wrong-import-position
    TOPIC,
    FinancialPictureBook,
    PictureMirror,
    StateBusPictureSink,
)
from nixrisk.positions import (  # pylint: disable=wrong-import-position
    EntryOrderOrigins,
    PositionOriginWriter,
    UntradableSymbol,
)
from nixrisk.reservations import (  # pylint: disable=wrong-import-position
    ReservationLedger,
)
from nixrisk.seam import (  # pylint: disable=wrong-import-position
    PositionState,
    ProposedOrder,
    Side,
    StopMode,
)
from nixrisk.stops import StopBook  # pylint: disable=wrong-import-position
from nixrisk.wal import Plane1Wal, recover  # pylint: disable=wrong-import-position

SYMBOL = "MESU6"
TICK = 0.25
FILL_PRICE = 7800.0
MARGIN = 1000.0


def _order(coid: str, qty: int = 2, symbol: str = SYMBOL) -> ProposedOrder:
    return ProposedOrder(
        client_order_id=coid,
        strategy_id="strat-1",
        symbol=symbol,
        side=Side.LONG,
        qty=qty,
        margin_per_contract=MARGIN,
        stop_ticks=20,
        stop_mode=StopMode.FIXED,
        signal_ts=1000.0,
    )


class _NullCancel:
    def cancel_order(self, client_order_id: str) -> None:
        pass


# too-many-instance-attributes: fourteen, and every one is a REAL component of
# §3's entry seam that some assertion below reads — the publisher, the picture, the
# subscriber, the mirror, the WAL, the enqueuer, the reservation ledger, the
# approved-order book, the stop book, the execution ledger, the origin registry,
# the origin writer, the fill handler and the sink. The whole claim is that NONE of
# them reads open off an ack, so dropping one to satisfy a count would drop a
# surface from the measurement.
class _Rig:  # pylint: disable=too-many-instance-attributes
    """The whole entry seam, on a REAL `ipc://` bus and a REAL on-disk WAL.

    Nothing here is a double for a module whose property is under test: the claim
    is about what §3's table, §12.7's mirror and §9's WAL hold, and a fake for any
    of the three would make the claim about the fake.
    """

    def __init__(self, tmp_path: Path, tag: str, *, margins: dict[str, float]) -> None:
        endpoint = f"ipc://{tmp_path}/{tag}.ipc"
        self.publisher = statebus.StatePublisher(endpoint)
        self.picture = FinancialPictureBook(
            balance=50000.0,
            deployable_fraction=0.70,
            sink=StateBusPictureSink(self.publisher),
        )
        self.picture.commit(margin_per_contract=margins)
        self.subscriber = statebus.StateSubscriber(endpoint, [TOPIC])
        self.mirror = PictureMirror(self.subscriber, max_age_s=600.0)
        seen = 0
        for _ in range(60):
            self.publisher.service(25)
            seen = self.publisher.subscribes_seen
            if seen:
                break
        assert seen, (
            "the real subscriber never reached the publisher, so the Allocator "
            "mirror below would be empty for a TRANSPORT reason and every "
            "'no open position' reading would be vacuous"
        )
        self.wal = Plane1Wal(str(tmp_path / f"{tag}.wal"))
        self.plane1 = Plane1Enqueuer(self.wal)
        self.reservations = ReservationLedger(self.plane1)
        self.orders = ApprovedOrderBook()
        self.stops = StopBook({SYMBOL: TICK})
        self.executions = ExecutionLedger()
        self.origins = EntryOrderOrigins()
        self.writer = PositionOriginWriter(
            picture=self.picture,
            ledger=self.executions,
            stops=self.stops,
            origins=self.origins,
        )
        self.handler = FillHandler(
            orders=self.orders,
            stops=self.stops,
            remainder=IocRemainder(
                reservations=self.reservations,
                cancels=_NullCancel(),
                clock=time.time,
            ),
            writer=self.writer,
        )
        self.sink = LimiterFillSink(
            handler=self.handler, orders=self.orders, clock=time.time
        )

    # -- the two events -----------------------------------------------------

    def ack(self, order: ProposedOrder) -> None:
        """THE PLACEMENT ACK: approved, origin recorded, reservation taken, order
        WORKING at the venue. No fill. Nothing here is a fill event."""
        self.orders.record(order)
        self.origins.record(order)
        self.reservations.take(order, time.time())
        self.picture.commit(sum_reservations=self.reservations.total_reserved())

    def fill(self, coid: str, exec_id: str, qty: int, cumulative: int) -> None:
        """One §2A `on_fill` broker event, through the production entry point."""
        self.sink.on_fill(coid, exec_id, SYMBOL, qty, FILL_PRICE, cumulative)

    # -- every surface a consumer could read as "open" ----------------------

    def surfaces(self) -> dict:
        self.mirror.drain(500)
        picture = self.picture.current()
        mirrored = self.mirror.picture()
        self.wal.sync_to_disk()
        return {
            "open_trades": [
                row.trade_id
                for row in picture.positions
                if row.state is PositionState.OPEN
            ],
            "sum_open_margin": picture.sum_open_margin,
            "sum_reservations": picture.sum_reservations,
            "committed": picture.committed,
            "reservations_outstanding": sorted(
                r.client_order_id for r in self.reservations.outstanding()
            ),
            "armed_stops": [s.client_order_id for s in self.stops.stops()],
            "ledger_net_qty": self.executions.position(SYMBOL).net_qty,
            "ledger_is_flat": self.executions.position(SYMBOL).is_flat,
            "mirror_open_trades": (
                [
                    row.trade_id
                    for row in mirrored.positions
                    if row.state is PositionState.OPEN
                ]
                if mirrored is not None
                else None
            ),
            "mirror_sum_open_margin": (
                mirrored.sum_open_margin if mirrored is not None else None
            ),
            "wal_kinds": [r.kind.value for r in recover(self.wal.path).rows],
        }

    def close(self) -> None:
        for closer in (self.subscriber.close, self.publisher.close):
            # Teardown must not mask a test's real verdict, and a socket already
            # closed is not news. `suppress` rather than try/except/pass so bandit
            # can tell a deliberate teardown from a swallowed error (B110).
            with contextlib.suppress(Exception):
                closer()


@pytest.fixture(name="rig")
def _rig_factory(tmp_path):
    """Builds rigs and CLOSES every socket, whatever the test does."""
    built: list[_Rig] = []

    def build(tag: str, *, margins: dict[str, float] | None = None) -> _Rig:
        made = _Rig(
            tmp_path, tag, margins={SYMBOL: MARGIN} if margins is None else margins
        )
        built.append(made)
        return made

    yield build
    for made in built:
        made.close()


# ==========================================================================
# THE FLAGSHIP — both halves, ack first
# ==========================================================================


def test_an_ACK_reads_OPEN_NOWHERE_and_a_FILL_reads_OPEN_EVERYWHERE(rig) -> None:
    """§14:970. Every ack assertion is PAIRED with the fill reading that moves it.

    §7.12: an ack half alone cannot tell a correct Limiter from a broken rig, and a
    fill half alone cannot tell a correct Limiter from an optimistic one. The pair
    is the measurement. The mirror is a REAL subscriber on a REAL socket (the
    fixture proves the subscription landed), so `mirror_open_trades == []` is a
    statement about §12.7's wire and not about a local object."""
    subject = rig("flagship")
    order = _order("c-1")

    # ---- HALF ONE: the ACK. Nothing may read open. ----
    subject.ack(order)
    acked = subject.surfaces()

    assert acked["open_trades"] == [], (
        f"§3's position table reads OPEN for {acked['open_trades']} on a PLACEMENT "
        "ACK — §14:970 makes open mean confirmed fill only"
    )
    assert acked["sum_open_margin"] == 0.0, (
        f"Σ open margin is {acked['sum_open_margin']} with nothing filled; §15 C1 "
        "counts a pending order under Σ RESERVATIONS, never under open margin"
    )
    assert acked["sum_reservations"] == MARGIN * order.qty, acked
    assert acked["committed"] == acked["sum_reservations"], (
        "committed on an ack must be exactly the pending reservation (§15 C1), "
        f"got committed={acked['committed']} Σres={acked['sum_reservations']}"
    )
    assert acked["reservations_outstanding"] == ["c-1"], acked
    assert acked["armed_stops"] == [], (
        f"a synthetic stop is armed ({acked['armed_stops']}) for a position no fill "
        "confirmed — §4 converts distance→price ONCE, AT the confirmed fill"
    )
    assert acked["ledger_is_flat"] is True and acked["ledger_net_qty"] == 0, acked
    assert acked["mirror_open_trades"] == [], (
        f"§12.7's Allocator mirror reads OPEN for {acked['mirror_open_trades']} off "
        "a placement ack"
    )
    assert acked["mirror_sum_open_margin"] == 0.0, acked
    assert "filled" not in acked["wal_kinds"], acked["wal_kinds"]
    assert subject.writer.writes == 0 and subject.sink.delivered == 0, (
        f"writes={subject.writer.writes} delivered={subject.sink.delivered}"
    )

    # ---- HALF TWO: the CONFIRMED FILL. Every one of those readings must move. ----
    subject.fill("c-1", "e-1", 2, 2)
    filled = subject.surfaces()

    assert filled["open_trades"] == ["c-1"], (
        "a confirmed fill did NOT produce an open row, so half one above proves "
        f"nothing: {filled}"
    )
    assert filled["sum_open_margin"] == MARGIN * order.qty, filled
    assert filled["sum_reservations"] == 0.0, (
        "§3: the reservation is released ON FILL and converts to open margin; "
        f"Σres is still {filled['sum_reservations']}"
    )
    assert filled["reservations_outstanding"] == [], filled
    assert filled["armed_stops"] == ["c-1"], filled
    assert filled["ledger_net_qty"] == 2 and filled["ledger_is_flat"] is False, filled
    assert filled["mirror_open_trades"] == ["c-1"], (
        f"§12.7's mirror did not receive the open position: {filled}"
    )
    assert filled["mirror_sum_open_margin"] == MARGIN * order.qty, filled
    assert subject.writer.writes == 1 and subject.sink.delivered == 1, (
        f"writes={subject.writer.writes} delivered={subject.sink.delivered}"
    )
    # committed is unchanged in TOTAL across the transition — the reservation
    # became open margin. §15 C1's whole point, and a double-count would show here.
    assert filled["committed"] == acked["committed"], (
        f"committed moved {acked['committed']} -> {filled['committed']} across a "
        "reservation→open-margin conversion; one of the two is double-counted"
    )


def test_the_TWO_ROUTES_an_ACK_could_take_into_the_FILL_PATH_are_REFUSED_BY_NAME(
    rig,
) -> None:
    """The structural half of §14:970: an ack is not merely unhandled, it is
    UNREPRESENTABLE. §7.12: asserting the refusal's exit path alone would pass for
    an instrument that broke, so both refusals are read for their REASON."""
    subject = rig("routes")
    subject.ack(_order("c-1"))

    with pytest.raises(InvalidExecutionReport) as zero:
        ExecutionReport(
            order_id="c-1",
            exec_id="ACK",
            symbol=SYMBOL,
            side=FillSide.BUY,
            filled_qty=0,
            price=FILL_PRICE,
            cumulative_qty=0,
            ts=1.0,
        )
    assert "filled_qty=0" in str(zero.value), str(zero.value)
    assert "a fill no arithmetic can see" in str(zero.value), str(zero.value)

    with pytest.raises(UnapprovedFill) as unapproved:
        subject.fill("never-approved", "e-1", 1, 1)
    assert "holds no approved order under that id" in str(unapproved.value), str(
        unapproved.value
    )


def test_OPEN_is_WRITTEN_at_EXACTLY_TWO_SITES_and_PENDING_at_NONE() -> None:
    """The mechanical enumeration behind the drive above, as a STANDING control.

    §7.12: the drives prove the shipped path is honest; they cannot prove a NEW
    path was not added next arc. This reads the tree instead. It is deliberately a
    `grep` over the real files rather than an import-time reflection: a site inside
    a branch nothing reaches is still a site, and only text finds it.

    If this reddens, read it as *"a third writer of OPEN exists — go prove it
    requires a confirmed fill"*, not as a failure."""
    out = subprocess.run(  # nosec B603,B607 - fixed argv, no shell
        [
            "grep",
            "-rn",
            "state=PositionState.OPEN",
            "--include=*.py",
            str(REPO / "scripts"),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    sites = {
        line.split(":")[0].replace(str(REPO) + "/", "")
        for line in out.stdout.strip().splitlines()
        if line and "/tests/" not in line
    }
    assert sites == {
        "scripts/nixrisk/positions.py",
        "scripts/nixrisk/projection.py",
    }, (
        f"the set of modules that WRITE PositionState.OPEN changed to {sorted(sites)}. "
        "positions.py writes it only from a fill the ExecutionLedger ingested; "
        "projection.py writes it only for a row folded from a `filled` Plane-1 "
        "event. A third writer must be shown to require a confirmed fill (§14:970)"
    )

    pending = subprocess.run(  # nosec B603,B607 - fixed argv, no shell
        [
            "grep",
            "-rn",
            "state=PositionState.PENDING",
            "--include=*.py",
            str(REPO / "scripts"),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    # `/tests/` is excluded for the same reason it is above: this file's own
    # grep argument is a literal match, and a control that reddens on its own
    # source text measures the harness rather than the tree.
    pending_sites = {
        line.split(":")[0].replace(str(REPO) + "/", "")
        for line in pending.stdout.strip().splitlines()
        if line and "/tests/" not in line
    }
    assert not pending_sites, (
        f"PositionState.PENDING now has a writer: {sorted(pending_sites)}. That is "
        "not automatically wrong — §3's table enumerates the state — but a pending "
        "row entering the published table is exactly where an optimistic open would "
        "first appear, so it must be driven"
    )


# ==========================================================================
# FC3 — an idempotent RE-DELIVERY of ONE execution
# ==========================================================================


class _PerDeliveryStamp(LimiterFillSink):
    """FC3's falsifier: the PRE-ARC-038 sink, stamping `ts` on every DELIVERY.

    Differs from the subject in one expression, which is the finding's whole site.
    """

    def on_fill(  # type: ignore[override]  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        client_order_id: str,
        exec_id: str,
        symbol: str,
        filled_qty: int,
        price: float,
        cumulative_qty: int,
    ) -> None:
        self._stamped.pop((client_order_id, exec_id), None)
        super().on_fill(
            client_order_id, exec_id, symbol, filled_qty, price, cumulative_qty
        )


def _sink_over(subject: _Rig, cls: type[LimiterFillSink]) -> LimiterFillSink:
    return cls(handler=subject.handler, orders=subject.orders, clock=time.time)


def test_a_RE_DELIVERED_FILL_is_a_DUPLICATE_not_a_CONTRADICTION(rig) -> None:
    """§15:1006's *"idempotent exec-report dedup"* and §12.4's reconnect case.
    BOTH HALVES.

    §7.12: `test_execution.py` proves duplicate-immunity at the LEDGER with
    hand-built reports that share a `ts` by construction, and `check_fill_handler`
    drives the SINK but only ever with a NEW `exec_id`. Neither can see a
    re-delivery of ONE execution through the layer that INVENTS the `ts`. So this
    re-sends the byte-identical §2A event through the sink."""
    # HALF ONE — the pre-fix stamp. The contradiction must APPEAR, by name.
    bad_rig = rig("redeliver-bad")
    bad_rig.ack(_order("c-dup", qty=3))
    bad_sink = _sink_over(bad_rig, _PerDeliveryStamp)
    bad_sink.on_fill("c-dup", "e-1", SYMBOL, 1, FILL_PRICE, 1)
    with pytest.raises(ContradictoryExecution) as caught:
        bad_sink.on_fill("c-dup", "e-1", SYMBOL, 1, FILL_PRICE, 1)
    assert "ts:" in str(caught.value), (
        f"the falsifier's contradiction was not about `ts` ({caught.value}) — it is "
        "not reproducing FC3"
    )
    assert "already reported with different data" in str(caught.value), str(
        caught.value
    )

    # HALF TWO — the shipped sink.
    subject = rig("redeliver-good")
    subject.ack(_order("c-dup", qty=3))
    subject.fill("c-dup", "e-1", 1, 1)
    first = subject.surfaces()
    subject.fill("c-dup", "e-1", 1, 1)  # the byte-identical event, again
    again = subject.surfaces()

    assert subject.executions.duplicates == 1, (
        "the ledger did not see a DUPLICATE; disposition/contradiction counters: "
        f"dup={subject.executions.duplicates} "
        f"contradictions={subject.executions.contradictions}"
    )
    assert subject.executions.contradictions == 0, (
        "a re-delivery of one execution was counted as a broker contradiction — "
        "§15's dedup is idempotent, not a rewrite"
    )
    assert subject.writer.duplicates == 1, subject.writer.duplicates
    assert again["ledger_net_qty"] == first["ledger_net_qty"] == 1, (first, again)
    assert again["sum_open_margin"] == first["sum_open_margin"], (first, again)
    assert subject.sink.delivered == 2, (
        "the sink stopped counting DELIVERIES, so a re-delivery became invisible: "
        f"{subject.sink.delivered}"
    )


def test_OUT_OF_ORDER_and_DUPLICATE_deliveries_leave_the_POSITION_correct(rig) -> None:
    """§4: the position derives from the SET of unique fills, so ordering cannot
    move it. §7.12: a monotone stream could not tell an order-independent sum from
    a last-write-wins one, so `e-3` is delivered BEFORE `e-2`, and the resulting
    venue-vs-ledger cumulative disagreement must be RECORDED rather than swallowed."""
    subject = rig("reorder")
    subject.ack(_order("c-ooo", qty=3))
    subject.fill("c-ooo", "e-1", 1, 1)
    subject.fill("c-ooo", "e-3", 1, 3)  # the LATER exec, delivered FIRST
    mid = subject.surfaces()
    subject.fill("c-ooo", "e-2", 1, 2)  # the one that was overtaken
    end = subject.surfaces()

    assert mid["ledger_net_qty"] == 2, mid
    assert end["ledger_net_qty"] == 3, end
    assert end["open_trades"] == ["c-ooo"], end
    assert end["sum_open_margin"] == 3 * MARGIN, end
    disagreements = subject.handler.disagreements()
    assert disagreements, (
        "out-of-order delivery necessarily makes the venue's cumulative disagree "
        "with the ledger's at least once, and nothing recorded it"
    )
    assert {(d.broker_cumulative, d.ledger_cumulative) for d in disagreements} == {
        (3, 2),
        (2, 3),
    }, [(d.broker_cumulative, d.ledger_cumulative) for d in disagreements]


# ==========================================================================
# FC4 — the converse: a real fill that reads FLAT everywhere. PINNED, NOT FIXED.
# ==========================================================================


def test_a_REFUSED_ORIGIN_WRITE_leaves_the_PICTURE_and_the_MIRROR_reading_FLAT(
    rig,
) -> None:
    """ARC 038 finding **FC4 — BLOCKS.** This control PINS the wrong state; it does
    not assert it is right.

    §14:968 makes flat the resolution of every uncertainty, and §14:970 makes open
    mean a confirmed fill — but a fill the `ExecutionLedger` has INGESTED while §3's
    published table shows nothing is the other error, and §7:501 prices bucket
    exposure from that table, so the held position is priced at ZERO and §7's cap
    ADMITS MORE (D3.136's failure mode). Discharging it needs an architect ruling
    on WHICH surface carries the condition (publish the row anyway, with what
    margin? or hand `nixrisk.flatten` an UNCERTAINTY trigger?) plus a consumer, and
    neither is a minimal local change to a frozen file. So the state is pinned:
    when ARC 039 repairs it, this test is the thing that must change, and it names
    what to change.

    §7.12: the CONTROL half is the identical drive with the margin PRESENT, which
    publishes the row — so this cannot pass because the rig is broken."""
    # CONTROL — the margin is known. The row is published.
    control = rig("fc4-control")
    control.ack(_order("c-ok"))
    control.fill("c-ok", "e-1", 2, 2)
    assert control.surfaces()["open_trades"] == ["c-ok"], (
        "the control rig did not publish an open row, so the arm below measures "
        "the rig and not the subject"
    )

    # SUBJECT — §4:198's not-tradable condition, mid-session.
    subject = rig("fc4-subject", margins={})
    subject.ack(_order("c-naked"))
    with pytest.raises(UntradableSymbol) as caught:
        subject.fill("c-naked", "e-1", 2, 2)
    assert "absent from the published margin field set" in str(caught.value), str(
        caught.value
    )

    state = subject.surfaces()
    # THE FILL IS A FACT.
    assert state["ledger_net_qty"] == 2, state
    assert subject.executions.fill_count() == 1, subject.executions.fill_count()
    # AND EVERY PUBLISHED SURFACE SAYS FLAT. This is the defect, pinned.
    assert state["open_trades"] == [], (
        "FC4 appears to be FIXED — §3's table now shows the position. If that is "
        "deliberate, this test is the one to rewrite, and the finding is discharged"
    )
    assert state["mirror_open_trades"] == [], (
        "FC4 appears to be FIXED at §12.7's mirror. Same instruction as above"
    )
    assert state["sum_open_margin"] == 0.0, state
    assert "filled" not in state["wal_kinds"], (
        f"§9 now records the fill ({state['wal_kinds']}) — part of FC4 is discharged"
    )
    # The stop IS armed, so the position is not unprotected while this process lives.
    assert state["armed_stops"] == ["c-naked"], state
    # The drift is VISIBLE to the ledger's own reconcile, and to nothing else.
    drifts = subject.executions.reconcile(subject.picture.current().positions)
    assert [(d.symbol, d.derived_net_qty, d.row_size, d.drift) for d in drifts] == [
        (SYMBOL, 2, 0, 2)
    ], [(d.symbol, d.derived_net_qty, d.row_size, d.drift) for d in drifts]
    # And the asymmetry that IS the finding: the sibling refusal records, this
    # one does not. `_refuse_unstopped` exists precisely so a supervising loop can
    # act on the condition; `UntradableSymbol` has no such surface.
    assert subject.writer.refusals == 1, subject.writer.refusals
    assert subject.writer.unstopped() == (), (
        "an escalation record now exists for this refusal — FC4's recording half "
        "is discharged and this assertion is the one to rewrite"
    )


def test_the_LEDGER_and_the_PICTURE_agree_on_the_HAPPY_PATH(rig) -> None:
    """The reconcile instrument FC4 leans on must be able to say AGREE, or its
    `drift=2` above is not information. §7.12: an instrument that always disagrees
    would make the assertion above meaningless."""
    subject = rig("agree")
    subject.ack(_order("c-ok"))
    subject.fill("c-ok", "e-1", 2, 2)
    drifts = subject.executions.reconcile(subject.picture.current().positions)
    assert [d.agrees for d in drifts] == [True], [
        (d.symbol, d.derived_net_qty, d.row_size) for d in drifts
    ]


def test_the_LEDGER_refuses_an_ACK_shaped_report_even_HAND_BUILT() -> None:
    """The last route: bypass the sink entirely. §7.12: everything above drives the
    seam, so a consumer building a report by hand is the one path not covered."""
    ledger = ExecutionLedger()
    good = ExecutionReport(
        order_id="c-1",
        exec_id="e-1",
        symbol=SYMBOL,
        side=FillSide.BUY,
        filled_qty=1,
        price=FILL_PRICE,
        cumulative_qty=1,
        ts=1.0,
    )
    assert ledger.ingest(good).disposition is IngestDisposition.APPLIED
    assert ledger.position(SYMBOL).net_qty == 1

    for qty, cumulative in ((0, 0), (-1, 5)):
        with pytest.raises(InvalidExecutionReport) as caught:
            ExecutionReport(
                order_id="c-1",
                exec_id=f"ack-{qty}",
                symbol=SYMBOL,
                side=FillSide.BUY,
                filled_qty=qty,
                price=FILL_PRICE,
                cumulative_qty=cumulative,
                ts=1.0,
            )
        assert f"filled_qty={qty}" in str(caught.value), str(caught.value)
    assert ledger.position(SYMBOL).net_qty == 1, "a refused report moved the position"
