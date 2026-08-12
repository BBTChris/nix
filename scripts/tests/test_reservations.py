"""ARC 028 / B — the reservation ledger driven directly.

`test_check_reservation_lifecycle.py` is the SHIPPED GATE's can-fail suite and
owns the §14 exactly-once property over §3's spec-parsed path set. This file is
the module's own suite and owns the things a gate should not: conformance to the
FROZEN port's signatures, the §3/§4 guards, and the two MEASUREMENTS that decide
how the gate had to be built.

**Every control asserts the REASON** — the message, the field, or the arithmetic
— never the exception type alone (check contract v2 §11).
"""
# pylint: disable=invalid-name,redefined-outer-name

from __future__ import annotations

import inspect
import math
import re
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from nixrisk.reservations import (  # pylint: disable=wrong-import-position
    AUDIT_TOLERANCE,
    MIN_MARGIN,
    DoubleRelease,
    DuplicateReservation,
    InvalidReservation,
    RefusalKind,
    ReservationLedger,
    UnknownReservation,
)
from nixrisk.seam import (  # pylint: disable=wrong-import-position
    EventKind,
    EventRow,
    ProposedOrder,
    ReservationLedgerPort,
    ReservationState,
    Side,
    StopMode,
    TerminalPath,
)

SPEC = REPO / "docs" / "nics_risk_subsystem_spec_v1.3.md"


class Recorder:
    """A Plane-1 sink that keeps every row. §9's `enqueue`, no durability."""

    def __init__(self) -> None:
        self.rows: list[EventRow] = []

    def enqueue(self, row: EventRow) -> None:
        """§9's hot half: a bounded append, no durability."""
        self.rows.append(row)

    def sync_to_disk(self) -> int:
        """Nothing is made durable here; the tests read `rows` directly."""
        return 0

    def pending(self) -> int:
        """Every row is pending — this sink never syncs."""
        return len(self.rows)

    def of(self, kind: EventKind) -> list[EventRow]:
        """Every row of one §12.10 kind, in arrival order."""
        return [row for row in self.rows if row.kind is kind]


def order(tag: str, qty: int = 3, per_contract: float = 1234.5) -> ProposedOrder:
    """One §3 proposal, already sized, with a non-round positive margin."""
    return ProposedOrder(
        client_order_id=tag,
        strategy_id="strat-1",
        symbol="ESZ6",
        side=Side.LONG,
        qty=qty,
        margin_per_contract=per_contract,
        stop_ticks=20,
        stop_mode=StopMode.FIXED,
        signal_ts=1000.0,
    )


@pytest.fixture
def rec() -> Recorder:
    """A fresh Plane-1 sink per test."""
    return Recorder()


@pytest.fixture
def ledger(rec: Recorder) -> ReservationLedger:
    """A fresh ledger writing into `rec`."""
    return ReservationLedger(rec)


# --------------------------------------------------------------------------
# THE FROZEN PORT — conformance MEASURED, never claimed by inheritance
# --------------------------------------------------------------------------


def _port_methods() -> list[str]:
    """Derived from the Protocol itself, so a method added there is required."""
    return sorted(
        name
        for name, value in vars(ReservationLedgerPort).items()
        if not name.startswith("_") and inspect.isfunction(value)
    )


def test_the_LEDGER_matches_the_FROZEN_PORT_signature_for_signature() -> None:
    """A ledger the seam's declaration does not describe is a second authority."""
    names = _port_methods()

    assert len(names) >= 4, f"the port declares only {names} — nothing to conform to"
    for name in names:
        port = inspect.signature(getattr(ReservationLedgerPort, name))
        assert hasattr(ReservationLedger, name), f"the ledger declares no {name}"
        impl = inspect.signature(getattr(ReservationLedger, name))
        assert impl == port, (
            f"{name}: the ledger declares {impl} and the frozen port declares {port}"
        )


def test_EVERY_PORT_VERB_is_SYNCHRONOUS_on_BOTH_SIDES_of_the_seam() -> None:
    """§11's entry pathway is cache reads + arithmetic; a coroutine has no
    bounded cost, and an awaitable `take` admits a second pass reading a Σ that
    does not include the first pass's approval.

    **BOTH sides are asserted, and the second half exists because of a MEASURED
    GAP.** `check_limiter_seam` guards `TerminalPath` against §3's sentence and
    bans behaviour in the seam — it does NOT read the sync/async declaration.
    Measured ARC 028 (B): a copy of the frozen seam with all four
    `ReservationLedgerPort` verbs rewritten to `async def` runs GREEN through
    that gate, and so does a copy with `ProposedOrder.margin_per_contract`
    deleted. The seam's most argued-for property is guarded by nothing, and this
    control closes exactly the reservation-port slice of it. CHECK-DEBT D3.56.
    """
    for name in _port_methods():
        declared = getattr(ReservationLedgerPort, name)
        assert not inspect.iscoroutinefunction(declared), (
            f"the FROZEN seam declares {name} as a coroutine — §11's O(1) claim "
            "over a suspendable call is unfalsifiable"
        )
        assert not inspect.iscoroutinefunction(getattr(ReservationLedger, name)), (
            f"the ledger implements {name} as a coroutine"
        )


def test_the_LEDGER_does_NOT_INHERIT_the_Protocol() -> None:
    """A Protocol's method bodies are docstrings. Inheriting it means a verb the
    ledger forgot to override returns None, silently, at the point of use."""
    assert ReservationLedgerPort not in ReservationLedger.__mro__, (
        ReservationLedger.__mro__
    )


# --------------------------------------------------------------------------
# §14 — EXACTLY ONE terminal release, over the SPEC's path set
# --------------------------------------------------------------------------


def _spec_paths() -> set[str]:
    """§3's release sentence, parsed here so this file's set is not the enum's."""
    match = re.search(
        r"released on:(?P<paths>.*?)\.\s", SPEC.read_text(encoding="utf-8"), re.DOTALL
    )
    assert match is not None, "§3's 'released on:' sentence is not in the frozen spec"
    words = [
        re.sub(r"\(.*?\)", " ", part).strip().lower()
        for part in match.group("paths").split(",")
        if part.strip()
    ]
    return {
        "_".join(
            w
            for w in re.split(r"[\s\-]+", phrase)
            if w and w not in ("resolution", "cancellation")
        ).upper()
        for phrase in words
    }


def test_EVERY_SPEC_NAMED_PATH_releases_ONCE_and_returns_the_capital(
    rec: Recorder,
) -> None:
    """The path set comes from §3's own sentence, never from TerminalPath.

    A LOOP rather than `@pytest.mark.parametrize`, deliberately. The argvalues
    would have to be `sorted(_spec_paths())`, and `check_derived_claims`'s
    `pytest_collected_tests` probe counts tests by AST — a non-literal argvalues
    makes that probe UNMEASURABLE, which is this arc blinding an existing
    instrument to make its own file prettier. Measured: the probe reported
    `parametrize argvalues is not a literal sequence` on the first spelling.
    """
    paths = sorted(_spec_paths())
    assert len(paths) >= 3, paths
    for index, path_name in enumerate(paths):
        via = getattr(TerminalPath, path_name)
        ledger = ReservationLedger(rec)
        taken = ledger.take(order(f"c-{index}"), 1.0)
        assert ledger.total_reserved() == taken.margin

        released = ledger.resolve(f"c-{index}", via, 2.0).released

        assert released is not None, f"§3 names {path_name} and the ledger refused it"
        assert released.state is ReservationState.RELEASED, released
        assert released.released_via is via, released
        assert released.released_ts == 2.0, released
        assert ledger.total_reserved() == 0.0, ledger.audit()
        assert not ledger.outstanding(), ledger.outstanding()
    assert len(rec.of(EventKind.RESERVATION_RELEASED)) == len(paths), rec.rows


def test_a_SECOND_TERMINAL_EVENT_on_ANY_PATH_is_refused_and_NAMES_the_first() -> None:
    """§4's remainder-cancel-after-fill race, generalised to every §3 path."""
    for index, path_name in enumerate(sorted(_spec_paths())):
        via = getattr(TerminalPath, path_name)
        rec = Recorder()
        ledger = ReservationLedger(rec)
        ledger.take(order(f"c-{index}"), 1.0)
        first = ledger.resolve(f"c-{index}", via, 2.0).released
        assert first is not None

        refusal = ledger.resolve(f"c-{index}", TerminalPath.CANCEL, 3.0).refusal

        assert refusal is not None, f"{path_name}: the second event was ACCEPTED"
        assert refusal.kind is RefusalKind.ALREADY_TERMINAL, refusal
        assert refusal.already_via is via, refusal
        assert refusal.reservation_id == first.reservation_id, refusal
        assert via.value in refusal.reason, refusal.reason
        assert ledger.total_reserved() == 0.0, ledger.audit()
        assert len(rec.of(EventKind.RESERVATION_RELEASED)) == 1, rec.rows


def test_the_PORT_S_release_RAISES_on_a_double_release_and_NAMES_the_prior_path(
    ledger: ReservationLedger,
) -> None:
    """The seam declares it: 'Raises on unknown id and on double release'."""
    taken = ledger.take(order("c-1"), 1.0)
    ledger.release(taken.reservation_id, TerminalPath.FILL, 2.0)

    with pytest.raises(DoubleRelease) as caught:
        ledger.release(taken.reservation_id, TerminalPath.CANCEL, 3.0)

    assert "already released via fill" in str(caught.value), str(caught.value)
    assert "EXACTLY ONE terminal release" in str(caught.value), str(caught.value)
    assert ledger.total_reserved() == 0.0, ledger.audit()


def test_an_UNKNOWN_reservation_id_RAISES_and_says_it_was_never_minted(
    ledger: ReservationLedger,
) -> None:
    """An id this ledger never minted is not a silent no-op."""
    with pytest.raises(UnknownReservation) as caught:
        ledger.release("RSV-99999999", TerminalPath.FILL, 1.0)

    assert "never minted" in str(caught.value), str(caught.value)


# --------------------------------------------------------------------------
# THE ASYMMETRY, MEASURED — and the intuitive ordering is BACKWARDS
# --------------------------------------------------------------------------


def test_a_DOUBLE_RELEASE_is_LOUD_to_the_SS11_7_reconcile(
    ledger: ReservationLedger,
) -> None:
    """It breaks `Σ == fsum(TAKEN)` at the instant it happens, by the exact
    double-released margin. §11.7's audit sees it on the very next cycle."""
    taken = ledger.take(order("c-1"), 1.0)
    ledger.take(order("c-2", qty=1, per_contract=2345.75), 1.0)
    ledger.resolve("c-1", TerminalPath.FILL, 2.0)
    # The defect, injected at the ledger's own aggregate rather than through a
    # public verb, because the shipped verbs REFUSE it — which is the point.
    ledger._sigma -= taken.margin  # pylint: disable=protected-access

    audit = ledger.audit()

    assert audit.drift == pytest.approx(-taken.margin), audit
    assert audit.material is True, audit
    assert abs(audit.drift) > AUDIT_TOLERANCE * 1e6, audit


def test_a_LEAK_is_SILENT_to_the_SS11_7_reconcile_and_the_BRIEF_is_BACKWARDS(
    ledger: ReservationLedger,
) -> None:
    """THE REFUTATION, and it is a measurement.

    The intuitive claim — *a leak is loud, eventually; a double release is
    silent* — is half right and half backwards. Against the ONE standing
    instrument the spec mandates for aggregates (§11.7's full-scan reconcile),
    a leaked reservation is a perfectly ordinary TAKEN row: it sums into the
    incremental aggregate and into the full scan identically. Drift is exactly
    0.0. The audit is STRUCTURALLY BLIND to it, forever, at any scale.

    So the double release is the loud one (it breaks an identity a standing
    detector checks) and the leak is the silent one (it breaks no identity and
    only shows up as capital starvation that looks like conservative sizing).
    Two defects, two instruments — which is why the gate does not rely on
    `audit()` for the leak direction and drives every §3 path explicitly.
    """
    for index in range(20):
        ledger.take(order(f"c-{index}", qty=index + 1), 1.0)
    # Nineteen orders reach a terminal event. One never does — the Limiter's
    # handler was never called, which is what a real leak looks like.
    for index in range(19):
        ledger.resolve(f"c-{index}", TerminalPath.FILL, 2.0)

    audit = ledger.audit()

    assert audit.outstanding == 1, audit
    assert audit.aggregate > 0.0, audit
    assert audit.drift == 0.0, (
        f"the leak must be arithmetically INVISIBLE to §11.7 — drift {audit.drift!r}"
    )
    assert audit.material is False, audit
    assert audit.aggregate == pytest.approx(audit.scanned, abs=AUDIT_TOLERANCE), audit


# --------------------------------------------------------------------------
# §11.3 — Σ is INCREMENTAL, proven by the float drift a derived Σ cannot have
# --------------------------------------------------------------------------


def test_SIGMA_is_a_RUNNING_AGGREGATE_and_not_a_SCAN_of_the_store(
    ledger: ReservationLedger,
) -> None:
    """A direct, behavioural measurement rather than a reading of the source.

    `+=` then `-=` over binary floats does not land on the same bits as
    `math.fsum` over the survivors. A Σ DERIVED from the store would be
    bit-identical to the scan by construction; an incremental one carries a
    tiny, real residue. That residue is the proof, and it is also why §11.7's
    reconcile has a tolerance at all.
    """
    ledger.take(order("c-1", qty=1, per_contract=0.1), 1.0)
    ledger.take(order("c-2", qty=1, per_contract=0.2), 1.0)
    ledger.resolve("c-1", TerminalPath.FILL, 2.0)

    audit = ledger.audit()

    assert audit.scanned == math.fsum([0.2]), audit
    assert audit.aggregate != audit.scanned, (
        "incremental Σ and the full scan are bit-identical — the aggregate is "
        "being computed FROM the store, which makes §11.7's reconcile compare a "
        "value with itself"
    )
    assert 0.0 < abs(audit.drift) <= AUDIT_TOLERANCE, audit
    assert audit.material is False, audit


def test_the_AUDIT_TOLERANCE_cannot_swallow_the_SMALLEST_ADMISSIBLE_release() -> None:
    """The noise floor must sit far below the smallest defect it must not hide."""
    assert MIN_MARGIN > AUDIT_TOLERANCE * 1e5, (MIN_MARGIN, AUDIT_TOLERANCE)


# --------------------------------------------------------------------------
# §3 / §4 GUARDS
# --------------------------------------------------------------------------


def test_a_FILL_releases_the_WHOLE_reservation_at_the_FILL_INSTANT(
    ledger: ReservationLedger, rec: Recorder
) -> None:
    """§4: 'the reservation for the unfilled portion released ... the instant
    reality comes in under the reservation, not on a delay'. The ledger is told
    the fill happened; it is not told how much filled, because the filled
    portion becomes OPEN MARGIN and belongs to the position table."""
    taken = ledger.take(order("c-1", qty=5, per_contract=1000.0), 1.0)
    assert ledger.total_reserved() == 5000.0

    released = ledger.resolve("c-1", TerminalPath.FILL, 2.0, reason="filled 2 of 5")

    assert released.released is not None
    assert ledger.total_reserved() == 0.0, (
        "the over-reserved capital must return to deployable whole, at the fill"
    )
    assert released.released.margin == taken.margin
    row = rec.of(EventKind.RESERVATION_RELEASED)[0]
    assert row.reason == "filled 2 of 5", row


def test_a_LATE_REMAINDER_CANCEL_after_a_PARTIAL_FILL_is_refused_not_absorbed(
    ledger: ReservationLedger,
) -> None:
    """§4: 'If the cancel loses the race and the remainder fills...'. This is
    the realistic double-release site, and it must not move Σ."""
    ledger.take(order("c-1", qty=5, per_contract=1000.0), 1.0)
    ledger.resolve("c-1", TerminalPath.FILL, 2.0)
    before = ledger.total_reserved()

    refusal = ledger.resolve("c-1", TerminalPath.CANCEL, 3.0).refusal

    assert refusal is not None, "the remainder-cancel was absorbed as a release"
    assert refusal.already_via is TerminalPath.FILL, refusal
    assert "Σ is unchanged" in refusal.reason, refusal.reason
    assert ledger.total_reserved() == before


def test_a_TERMINAL_EVENT_for_an_order_NEVER_RESERVED_is_a_DISTINCT_refusal(
    ledger: ReservationLedger,
) -> None:
    """Legitimate for an order denied before Phase B — and the exact signature
    of a ledger whose take and resolve key on different things, which would leak
    every reservation while reporting every event handled. The two kinds must be
    tellable apart or the second hides behind the first."""
    refusal = ledger.resolve("never-seen", TerminalPath.REJECT, 1.0).refusal

    assert refusal is not None
    assert refusal.kind is RefusalKind.NEVER_RESERVED, refusal
    assert refusal.kind is not RefusalKind.ALREADY_TERMINAL
    assert "no reservation was ever taken" in refusal.reason, refusal.reason
    assert ledger.total_reserved() == 0.0


def test_a_SECOND_TAKE_for_a_LIVE_client_order_id_RAISES_and_cites_one_in_flight(
    ledger: ReservationLedger,
) -> None:
    """§4: one in-flight action per strategy, so a second take is a defect."""
    ledger.take(order("c-1"), 1.0)

    with pytest.raises(DuplicateReservation) as caught:
        ledger.take(order("c-1"), 2.0)

    assert "already holds live reservation" in str(caught.value), str(caught.value)
    assert "in-flight action per strategy" in str(caught.value), str(caught.value)


def test_REUSING_a_client_order_id_after_a_TERMINAL_PATH_RAISES(
    ledger: ReservationLedger,
) -> None:
    """A reused id would let a fresh reservation inherit a terminal record, and
    the next duplicate event would be refused against the WRONG order."""
    ledger.take(order("c-1"), 1.0)
    ledger.resolve("c-1", TerminalPath.FILL, 2.0)

    with pytest.raises(DuplicateReservation) as caught:
        ledger.take(order("c-1"), 3.0)

    assert "already reached terminal path" in str(caught.value), str(caught.value)


@pytest.mark.parametrize("margin", [0.0, -1.0, MIN_MARGIN / 2, float("inf")])
def test_a_MARGIN_NO_ARITHMETIC_CAN_SEE_is_REFUSED_at_take(
    margin: float, ledger: ReservationLedger
) -> None:
    """A zero-margin reservation makes every Σ assertion `0 == 0` and every
    double release of it invisible. §3's ingress guard, one layer in."""
    with pytest.raises(InvalidReservation) as caught:
        ledger.take(order("c-1", qty=1, per_contract=margin), 1.0)

    assert "is not a finite figure at or above MIN_MARGIN" in str(caught.value), str(
        caught.value
    )
    assert ledger.total_reserved() == 0.0


# --------------------------------------------------------------------------
# §9 / §12.10 — the Plane-1 rows
# --------------------------------------------------------------------------


def test_TAKE_and_RELEASE_each_book_ONE_PLANE1_ROW_carrying_SS9_s_fields(
    ledger: ReservationLedger, rec: Recorder
) -> None:
    """§12.10 books `reservation taken / released` on Plane 1; §9 requires
    timestamp + strategy_id + reason on every row. `trade_id` is absent by
    design — it is minted at OPEN (§4) and a reservation has not opened."""
    taken = ledger.take(order("c-1"), 1000.0)
    ledger.resolve("c-1", TerminalPath.FILL, 2000.0)

    assert [row.kind for row in rec.rows] == [
        EventKind.RESERVATION_TAKEN,
        EventKind.RESERVATION_RELEASED,
    ], rec.rows
    for row in rec.rows:
        assert row.strategy_id == "strat-1", row
        assert row.reason, "§9 requires a reason on every row"
        assert row.trade_id is None, row
        assert row.fields["reservation_id"] == taken.reservation_id, row
        assert row.fields["client_order_id"] == "c-1", row
    assert rec.rows[0].ts == 1000.0 and rec.rows[1].ts == 2000.0, rec.rows
    assert rec.rows[0].fields["via"] == "", rec.rows[0]
    assert rec.rows[1].fields["via"] == "fill", rec.rows[1]
    assert float(rec.rows[0].fields["sum_reservations"]) == taken.margin
    assert float(rec.rows[1].fields["sum_reservations"]) == 0.0


def test_a_REFUSED_DUPLICATE_books_NO_PLANE1_ROW_which_is_a_SPEC_FINDING(
    ledger: ReservationLedger, rec: Recorder
) -> None:
    """FINDING ABOUT THE SPEC, recorded as a control so it cannot be forgotten.

    §14 requires exactly one terminal release. §12.10's inventory books
    `reservation taken / released` and nothing else this ledger can write. So the
    one event that PROVES the invariant was enforced against §4's own documented
    race — the refused duplicate — has no Plane-1 row, and is invisible in the
    auditable record of money truth. It is kept in memory here and surfaced
    through `audit().refused`. Mapping it onto the existing `drift-audit event`
    row is an architect's call; this module refuses to invent a row the spec's
    inventory does not name. CHECK-DEBT D3.52.
    """
    ledger.take(order("c-1"), 1.0)
    ledger.resolve("c-1", TerminalPath.FILL, 2.0)
    before = list(rec.rows)

    ledger.resolve("c-1", TerminalPath.CANCEL, 3.0)

    assert rec.rows == before, "a refusal must not be booked as a release"
    assert ledger.audit().refused == 1, ledger.audit()
    assert len(ledger.refusals()) == 1


def test_the_LEDGER_REQUIRES_a_PLANE1_SINK_and_does_not_default_to_a_black_hole() -> (
    None
):
    """§9: the Limiter is the SOLE writer of Plane 1. A ledger that quietly
    discarded its own audit rows would keep perfect books nobody can read."""
    with pytest.raises(TypeError):
        ReservationLedger()  # type: ignore[call-arg]  # pylint: disable=no-value-for-parameter
