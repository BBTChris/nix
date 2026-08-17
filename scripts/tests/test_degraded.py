"""`scripts/nixrisk/degraded.py` — §12.4's wiring, driven to both answers.

The module exists because two §12.4 facts reached nothing before it: a WAL that
cannot append halted no gate, and a §12.4 alert carried no §12.9 tier. Both of
those are properties of a WIRE, so every test here drives the wire in BOTH
directions — a degraded sink that must NOT halt beside a disk-critical WAL that
must, and a transcribed tier beside a derived one.

The one assertion that is not about behaviour is deliberate:
`test_the_halt_flag_satisfies_the_REAL_gate_HaltFlagPort` uses the actual
`nixrisk.gate.HaltFlagPort`, not a restatement of it. `degraded.py` cannot import
the gate (the gate imports the ledger which imports the seam, and this module is
imported by the gate's caller), so it declares the shape structurally — and a
declared shape that nobody compares against the real one is exactly how ARC 034's
integration found a changed signature that every branch's gates were green over.
"""

from __future__ import annotations

# pylint: disable=invalid-name,redefined-outer-name,missing-function-docstring
# pylint: disable=duplicate-code,too-few-public-methods
# `too-few-public-methods`: `_Sink`, `_Halt` and `_State` are one-verb ports
# standing in for §12.9's alert transport and §12.4's persistence state.
# Test names SHOUT the property under measurement — the house convention, and
# what makes a red line readable without opening the file.
import inspect
import sys
import tempfile
import time
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts"))

# pylint: disable=wrong-import-position
from nixrisk.degraded import (  # pylint: disable=import-error
    ALERT_ROUTING,
    NATURAL_KEY_FIELD,
    UNROUTED,
    WAL_SEQ_FIELD,
    DegradedError,
    PersistenceAlerts,
    PersistenceHaltFlag,
    Plane1Enqueuer,
    TierSource,
    instrumented_wal,
    natural_key,
)
from nixrisk.gate import HaltFlagPort  # pylint: disable=import-error
from nixrisk.reservations import ReservationLedger  # pylint: disable=import-error
from nixrisk.seam import (  # pylint: disable=import-error
    EventKind,
    EventRow,
    Plane1Port,
    ProposedOrder,
    Side,
    StopMode,
)
from nixrisk.survival import Alert, AlertTier  # pylint: disable=import-error
from nixrisk.wal import (  # pylint: disable=import-error
    DiskCritical,
    PersistenceState,
    Plane1Wal,
    recover,
)


class _Sink:
    """A §12.9 `AlertSink` that keeps what it was handed."""

    def __init__(self) -> None:
        self.alerts: list[Alert] = []

    def emit(self, alert: Alert) -> None:
        self.alerts.append(alert)


class _Halt:
    """An upstream §12.5 HALT flag."""

    def __init__(self, halted: bool = False, why: str = "") -> None:
        self.value = (halted, why)

    def is_set(self) -> tuple[bool, str]:
        return self.value


class _State:
    """A `PersistenceStatePort` in whichever §12.4 state a test needs."""

    def __init__(self, state: PersistenceState, reason: str = "") -> None:
        self._state = state
        self._reason = reason

    def admits_new_entries(self) -> tuple[bool, str]:
        if self._state is PersistenceState.DISK_CRITICAL:
            return False, self._reason
        return True, self._reason

    @property
    def state(self) -> PersistenceState:
        return self._state


@pytest.fixture(name="walfile")
def _walfile():
    root = Path(tempfile.mkdtemp(prefix="nixdeg-"))
    yield root / "plane1.wal"
    for child in sorted(root.iterdir()):
        child.unlink()
    root.rmdir()


def _row(index: int, kind: EventKind = EventKind.SIGNAL) -> EventRow:
    return EventRow(
        kind=kind,
        ts=1_770_000_000.0 + index,
        strategy_id="s1",
        reason=f"row {index}",
        trade_id=f"T{index:04d}",
    )


# --------------------------------------------------------------- the halt wire


def test_the_halt_flag_satisfies_the_REAL_gate_HaltFlagPort() -> None:
    """Not a restatement of the port — the port itself.

    `degraded.py` declares `HaltReadPort` structurally because it cannot import
    the gate. This is the comparison that keeps the two from drifting apart in
    silence, which is the class of defect a blind four-branch merge produces.
    """
    flag = PersistenceHaltFlag(_State(PersistenceState.HEALTHY))
    assert isinstance(flag, HaltFlagPort)


def test_a_DEGRADED_SINK_is_NOT_a_HALT() -> None:
    """§12.4's headline, and the direction that gets got backwards.

    A Postgres outage that halted the gate would turn a database restart into a
    stopped business. The whole sentence is 'degraded persistence ≠ degraded
    trading'.
    """
    flag = PersistenceHaltFlag(
        _State(PersistenceState.SINK_DEGRADED, "sink is down, 40 rows buffering")
    )
    assert flag.is_set() == (False, "")


def test_a_DISK_CRITICAL_wal_HALTS_and_the_reason_NAMES_the_rule_and_the_cause() -> (
    None
):
    """The other half. §3 and §5 both require a denial to NAME the rule."""
    flag = PersistenceHaltFlag(
        _State(
            PersistenceState.DISK_CRITICAL,
            "§12.4 disk-critical: OSError errno=27 File too large",
        )
    )
    halted, why = flag.is_set()
    assert halted
    assert "persistence_disk_critical" in why
    assert "errno=27" in why


def test_an_upstream_OPERATOR_halt_is_NOT_dropped_by_the_composition() -> None:
    """`GatePass` takes ONE halt port, so composing must not silence §12.5."""
    flag = PersistenceHaltFlag(
        _State(PersistenceState.HEALTHY),
        upstream=_Halt(True, "operator HALT, cleared only by operator (§12.5)"),
    )
    halted, why = flag.is_set()
    assert halted
    assert "operator HALT" in why


def test_an_upstream_that_declares_no_is_set_is_REFUSED_at_construction() -> None:
    """Silently dropping §12.5 is strictly worse than refusing to compose."""
    healthy = _State(PersistenceState.HEALTHY)
    with pytest.raises(DegradedError, match="is_set"):
        PersistenceHaltFlag(healthy, upstream=object())  # type: ignore[arg-type]


def test_a_wal_that_cannot_report_its_state_is_REFUSED_at_construction() -> None:
    """A halt flag that cannot read the state never fires and looks like one that does."""
    with pytest.raises(DegradedError, match="PersistenceStatePort"):
        PersistenceHaltFlag(object())  # type: ignore[arg-type]


# -------------------------------------------------------------- the alert wire


def test_the_POSTGRES_OUTAGE_tier_is_TRANSCRIBED_from_12_9_verbatim() -> None:
    """§12.9's Warning list ends with 'Postgres down ⇒ degraded persistence'.

    Recorded as `SPEC_12_9` rather than a comment, because the difference between
    quoting the spec and making a ruling is the difference this arc must not blur.
    """
    rule = ALERT_ROUTING["wal_sink_degraded"]
    assert rule.tier is AlertTier.WARNING
    assert rule.source is TierSource.SPEC_12_9


def test_the_DISK_CRITICAL_tier_is_DERIVED_and_the_module_SAYS_SO() -> None:
    """§12.9 names NO tier for disk-critical and §12.5's setter list omits it.

    This is a spec gap. CRITICAL is the fail-closed choice — the halting failure
    cannot be quieter than the non-halting one — but it is a ruling and the code
    labels it as one.
    """
    rule = ALERT_ROUTING["wal_disk_critical"]
    assert rule.tier is AlertTier.CRITICAL
    assert rule.source is TierSource.DERIVED
    assert "§12.9 names no tier" in rule.citation


def test_an_UNROUTED_persistence_event_is_ESCALATED_not_dropped() -> None:
    """Fail closed and loud. A quiet default is an alert nobody was paged for."""
    assert UNROUTED.tier is AlertTier.CRITICAL
    sink = _Sink()
    alerts = PersistenceAlerts(sink)
    alerts.bind(_State(PersistenceState.HEALTHY))
    alerts("wal_something_nobody_added_to_the_table", "detail")
    assert sink.alerts[0].tier is AlertTier.CRITICAL


def test_the_alert_carries_the_SNAPSHOT_12_9_REQUIRES_not_just_a_code() -> None:
    """§12.9: 'the cause and the relevant snapshot values, not just a code'."""
    sink = _Sink()
    alerts = PersistenceAlerts(sink)
    alerts.bind(_State(PersistenceState.SINK_DEGRADED, "sink down"), backlog=lambda: 41)
    alerts("wal_sink_degraded", "connection refused")
    snapshot = sink.alerts[0].snapshot
    assert snapshot["cause"] == "connection refused"
    assert snapshot["wal_state"] == "sink_degraded"
    assert snapshot["backlog_rows"] == "41"
    assert snapshot["admits_new_entries"] == "True"


def test_an_alert_sink_that_cannot_emit_is_REFUSED_at_construction() -> None:
    """Constructing alerts and dropping them looks exactly like never alerting."""
    with pytest.raises(DegradedError, match="emit"):
        PersistenceAlerts(object())  # type: ignore[arg-type]


def test_instrumented_wal_ROUTES_a_real_disk_critical_to_CRITICAL(walfile) -> None:
    """End to end through the real `Plane1Wal`, not through the adapter alone."""
    sink = _Sink()
    wal, _alerts = instrumented_wal(str(walfile), sink)
    wal._go_critical(OSError(27, "File too large"))  # pylint: disable=protected-access
    assert [(a.tier, a.event) for a in sink.alerts] == [
        (AlertTier.CRITICAL, "wal_disk_critical")
    ]
    wal.close()


# ------------------------------------------------- §2.2's ordering + dedup keys


def test_the_enqueuer_STAMPS_wal_seq_and_natural_key_CONTIGUOUSLY(walfile) -> None:
    """Ordering is authoritative from the WAL sequence (schema spec §2.2)."""
    wal = Plane1Wal(str(walfile))
    enq = Plane1Enqueuer(wal)
    for index in range(5):
        enq.enqueue(_row(index))
    wal.sync_to_disk()
    rows = recover(walfile).rows
    assert [int(r.fields[WAL_SEQ_FIELD]) for r in rows] == [0, 1, 2, 3, 4]
    assert len({r.fields[NATURAL_KEY_FIELD] for r in rows}) == 5
    wal.close()


def test_the_natural_key_SURVIVES_a_round_trip_through_the_WAL(walfile) -> None:
    """Exactly-once is impossible unless the key is stable across re-delivery.

    A sink that minted the key at FLUSH time would give the same logical record a
    different key on the second delivery, the unique index would never fire, and
    dedup would be structurally impossible while every test looked fine.
    """
    wal = Plane1Wal(str(walfile))
    enq = Plane1Enqueuer(wal)
    enq.enqueue(_row(7))
    wal.sync_to_disk()
    first = recover(walfile).rows[0].fields[NATURAL_KEY_FIELD]
    second = recover(walfile).rows[0].fields[NATURAL_KEY_FIELD]
    assert first == second == natural_key(_row(7), 0)
    wal.close()


def test_a_PRODUCER_SUPPLIED_natural_key_is_LEFT_ALONE(walfile) -> None:
    """A broker execution id is a stronger identity than a WAL offset."""
    wal = Plane1Wal(str(walfile))
    enq = Plane1Enqueuer(wal)
    enq.enqueue(
        EventRow(
            kind=EventKind.SIGNAL,
            ts=1.0,
            strategy_id="s1",
            reason="r",
            trade_id="T1",
            fields={NATURAL_KEY_FIELD: "broker-exec-99"},
        )
    )
    wal.sync_to_disk()
    assert recover(walfile).rows[0].fields[NATURAL_KEY_FIELD] == "broker-exec-99"
    wal.close()


def test_a_DISK_CRITICAL_enqueue_does_NOT_consume_a_sequence_number(walfile) -> None:
    """A row that never reached the WAL has no WAL record number.

    Burning one for it would put a permanent hole in the ordering authority, and
    `wal_seq` contiguity is exactly what the reconnect gate asserts.
    """
    wal = Plane1Wal(str(walfile))
    enq = Plane1Enqueuer(wal)
    enq.enqueue(_row(0))
    assert enq.next_seq == 1
    wal._go_critical(OSError(28, "No space left on device"))  # pylint: disable=protected-access
    with pytest.raises(DiskCritical):
        enq.enqueue(_row(1))
    assert enq.next_seq == 1
    wal.close()


def test_the_enqueuer_RESUMES_the_sequence_from_the_WAL_ON_DISK(walfile) -> None:
    """A restarted Limiter must not re-issue sequence numbers already on disk."""
    wal = Plane1Wal(str(walfile))
    enq = Plane1Enqueuer(wal)
    for index in range(3):
        enq.enqueue(_row(index))
    wal.sync_to_disk()
    wal.close()

    resumed = Plane1Wal(str(walfile))
    assert Plane1Enqueuer(resumed).next_seq == 3
    resumed.close()


def test_the_enqueuer_satisfies_the_FROZEN_Plane1Port_BY_SIGNATURE(walfile) -> None:
    """It is a DECORATOR, not a new writer (§12.10: 'no new writers, ever').

    `Plane1Port` is deliberately NOT `@runtime_checkable`, so conformance is
    proven by comparing SIGNATURES against the frozen port — the same
    measurement `reservations.ReservationLedger` argues for in its own
    docstring, and a stronger one than an `isinstance` that only counts
    attribute names.
    """
    wal = Plane1Wal(str(walfile))
    enqueuer = Plane1Enqueuer(wal)
    for verb in ("enqueue", "sync_to_disk", "pending"):
        port_sig = inspect.signature(getattr(Plane1Port, verb))
        mine = inspect.signature(getattr(type(enqueuer), verb))
        assert mine == port_sig, (verb, mine, port_sig)
    wal.close()


def test_the_REAL_reservation_ledger_writes_THROUGH_it_unchanged(walfile) -> None:
    """The decorator claim, measured on a real producer rather than asserted.

    `ReservationLedger` authors its own §12.10 rows and knows nothing about
    `wal_seq`. If wrapping the port did not stamp them, every existing producer
    in the tree would emit rows that can be neither ordered nor deduplicated.
    """
    wal = Plane1Wal(str(walfile))
    ledger = ReservationLedger(Plane1Enqueuer(wal))
    ledger.take(
        ProposedOrder(
            client_order_id="c1",
            strategy_id="s1",
            symbol="ES",
            side=Side.LONG,
            qty=2,
            margin_per_contract=1000.0,
            stop_ticks=40,
            stop_mode=StopMode.FIXED,
            signal_ts=time.time(),
        ),
        time.time(),
    )
    wal.sync_to_disk()
    rows = recover(walfile).rows
    assert [r.kind for r in rows] == [EventKind.RESERVATION_TAKEN]
    assert rows[0].fields[WAL_SEQ_FIELD] == "0"
    assert rows[0].fields[NATURAL_KEY_FIELD].startswith("reservation_taken|s1|")
    wal.close()
