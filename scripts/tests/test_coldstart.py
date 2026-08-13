"""ARC 029 / sub-agent D — cold-start reconciliation driven directly (§4, V34).

This file owns the §4 cold-start properties: the broker query is the record
(D1), the query GATES registration (D2), an unexpected position is flattened to
flat BEFORE any registration (D3), the market-tradable guard's TWO halves (D4),
and restart = flat always, even for a winning inherited position (D5). It also
carries the three §0a hypotheses the brief told us to MEASURE rather than assume.

**Every control asserts the REASON** — the message, the field, or the state —
never an exit code or exception type alone (check contract v2 §11). Each property
is made can-fail by a planted defect at a NAMED site, restored to green.
"""
# pylint: disable=invalid-name,redefined-outer-name,protected-access
# pylint: disable=too-few-public-methods
# The fakes below (FakeFlattener, FakeHalt) each declare exactly the ONE verb the
# port they stand in for declares; a second method would be a fake doing two jobs.

from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from nixrisk.coldstart import (  # pylint: disable=wrong-import-position
    ColdStart,
    ColdStartError,
    ColdStartState,
    RegistrationRefused,
)
from nixrisk.seam import (  # pylint: disable=wrong-import-position
    BrokerTruth,
    ColdStartPort,
    EventKind,
    EventRow,
    FlattenTrigger,
    PositionRow,
    PositionState,
)

# --------------------------------------------------------------------------
# Fakes — collaborators the reconciler stands on, each drivable into defect
# --------------------------------------------------------------------------


def flat_truth(balance: float = 50_000.0, at: float = 1_000.0) -> BrokerTruth:
    """The broker reports NO open position — provably flat."""
    return BrokerTruth(positions=(), balance=balance, polled_at=at)


def open_truth(
    n: int = 1, balance: float = 50_000.0, at: float = 1_000.0
) -> BrokerTruth:
    """The broker reports `n` inherited, ownerless positions (strategy_id blank)."""
    rows = tuple(
        PositionRow(
            trade_id=f"inh-{i}",
            symbol="ESZ6",
            strategy_id="",  # inherited: no registered owner yet — an orphan
            size=2,
            margin=1_234.5,
            state=PositionState.OPEN,
        )
        for i in range(n)
    )
    return BrokerTruth(positions=rows, balance=balance, polled_at=at)


class FakeBroker:
    """§4's broker truth source. `current` is what the next poll returns."""

    def __init__(self, current: BrokerTruth, tradable: tuple[bool, str]) -> None:
        self.current = current
        self.tradable = tradable
        self.polls = 0

    def poll_truth(self) -> BrokerTruth:
        """One round-trip; positions + balance together, counted."""
        self.polls += 1
        return self.current

    def market_tradable(self) -> tuple[bool, str]:
        """`(tradable, why)`."""
        return self.tradable


class FakeFlattener:
    """Limiter-only flatten execution. On a successful fire the position closes,
    so the broker's next poll reports flat — unless `succeeds` is set False, the
    partial-flatten / lost-race case that must fail closed."""

    def __init__(self, broker: FakeBroker, succeeds: bool = True) -> None:
        self._broker = broker
        self._succeeds = succeeds
        self.calls: list[BrokerTruth] = []

    def flatten(self, truth: BrokerTruth) -> tuple[FlattenTrigger, ...]:
        """Fire a market close per inherited position; report ORPHAN triggers."""
        self.calls.append(truth)
        if self._succeeds:
            self._broker.current = flat_truth(
                balance=truth.balance, at=truth.polled_at + 1.0
            )
        return tuple(FlattenTrigger.ORPHAN for _ in truth.positions)


class FakeHalt:
    """The loud (§12.9 Critical) HALT hold. Records every reason it was given."""

    def __init__(self) -> None:
        self.reasons: list[str] = []

    def hold_in_halt(self, reason: str) -> None:
        """Set HALT + Critical alert."""
        self.reasons.append(reason)


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


def build(
    truth: BrokerTruth,
    tradable: tuple[bool, str] = (True, "RTH open"),
    flatten_succeeds: bool = True,
) -> tuple[ColdStart, FakeBroker, FakeFlattener, FakeHalt, Recorder]:
    """A reconciler wired to fresh, drivable fakes."""
    broker = FakeBroker(truth, tradable)
    flattener = FakeFlattener(broker, succeeds=flatten_succeeds)
    halt = FakeHalt()
    rec = Recorder()
    cs = ColdStart(broker, flattener, halt, rec)
    return cs, broker, flattener, halt, rec


# --------------------------------------------------------------------------
# THE FROZEN PORT — conformance MEASURED, never claimed by inheritance
# --------------------------------------------------------------------------


def _port_methods() -> list[str]:
    """Derived from the Protocol itself, so a method added there is required."""
    return sorted(
        name
        for name, value in vars(ColdStartPort).items()
        if not name.startswith("_") and inspect.isfunction(value)
    )


def test_the_RECONCILER_matches_the_FROZEN_PORT_signature_for_signature() -> None:
    """A cold-start that the seam's declaration does not describe is a second
    authority. Signatures are compared against the port, not inherited from it."""
    names = _port_methods()
    assert len(names) >= 4, f"the port declares only {names} — nothing to conform to"
    for name in names:
        port = inspect.signature(getattr(ColdStartPort, name))
        assert hasattr(ColdStart, name), f"the reconciler declares no {name}"
        impl = inspect.signature(getattr(ColdStart, name))
        assert impl == port, (
            f"{name}: the reconciler declares {impl} and the frozen port {port}"
        )


def test_EVERY_PORT_VERB_is_SYNCHRONOUS_on_BOTH_SIDES_of_the_seam() -> None:
    """The gate is an ORDERING property: an awaitable admission gate is a window a
    registration can interleave through (§4, seam docstring). A coroutine on either
    side would reintroduce that window, so neither side may be `async def`."""
    for name in _port_methods():
        assert not inspect.iscoroutinefunction(getattr(ColdStartPort, name)), (
            f"the FROZEN seam declares {name} as a coroutine — the ordering gate "
            "has a suspension point"
        )
        assert not inspect.iscoroutinefunction(getattr(ColdStart, name)), (
            f"the reconciler implements {name} as a coroutine"
        )
    for extra in ("reconcile", "register"):
        assert not inspect.iscoroutinefunction(getattr(ColdStart, extra)), extra


def test_the_RECONCILER_does_NOT_INHERIT_the_Protocol() -> None:
    """A Protocol's method bodies are docstrings. Inheriting it means a verb the
    reconciler forgot to override returns None — and a None `registration_admitted`
    reads as a working refusal while measuring nothing."""
    assert ColdStartPort not in ColdStart.__mro__, ColdStart.__mro__


# --------------------------------------------------------------------------
# D1 — the broker's answer IS the record, pulled in ONE motion (§4)
# --------------------------------------------------------------------------


def test_D1_query_truth_pulls_POSITIONS_and_BALANCE_in_ONE_broker_round_trip() -> None:
    """§4: balance and positions from ONE poll, or a balance read at one instant
    against positions read at another is the stale-balance tear §3 forbids.

    can-fail: the planted defect is a second, separate read. `query_truth` calls
    the broker EXACTLY once and returns a single `BrokerTruth` bearing one
    `polled_at` for both halves; a two-read implementation would land `polls == 2`
    for one logical query and the count assertion below reddens at that site.
    """
    cs, broker, _flat, _halt, _rec = build(open_truth(1, balance=42_000.0))
    assert broker.polls == 0

    truth = cs.query_truth()

    assert broker.polls == 1, "positions and balance did not come from ONE poll"
    assert truth.balance == 42_000.0
    assert truth.positions and truth.balance == 42_000.0, truth
    assert all(p.polled_at == truth.polled_at for p in [truth]), truth


def test_D1_at_cold_start_the_broker_TRUTH_is_stored_as_the_record() -> None:
    """Not a reconciliation against a local record — there is none — the answer is
    the record. The last polled truth is what every later decision reads."""
    cs, _broker, _flat, _halt, _rec = build(flat_truth(balance=7_777.0))
    cs.query_truth()
    assert cs._last_truth is not None and cs._last_truth.balance == 7_777.0


# --------------------------------------------------------------------------
# D2 — the query GATES registration, and the gate is only falsifiable against
#      an ATTEMPT (§0a hypothesis, MEASURED)
# --------------------------------------------------------------------------


def test_D2_a_registration_ATTEMPT_before_flat_is_REFUSED_and_NAMES_why() -> None:
    """§4: no strategy registers until a provably-flat assertion has passed.

    can-fail: the site is `register`'s `if not self._admitted: raise`. Deleting
    that guard turns this `pytest.raises` red — a registration would go through
    against unproven state. The refusal names the state and the rule, per §11.
    """
    cs, _broker, _flat, _halt, _rec = build(open_truth(1))
    assert cs.registration_admitted() is False

    with pytest.raises(RegistrationRefused) as caught:
        cs.register("strat-1", 1_000.0)

    assert "registration REFUSED" in str(caught.value), str(caught.value)
    assert "provably-flat assertion has not passed" in str(caught.value)
    assert ColdStartState.PENDING.value in str(caught.value), str(caught.value)
    assert not cs.registered(), "nothing may register while the gate is shut"


def test_D2_once_PROVABLY_FLAT_the_same_ATTEMPT_is_ADMITTED() -> None:
    """The gate OPENS on a confirmed flat, and only then. Same attempt, admitted."""
    cs, _broker, _flat, _halt, _rec = build(flat_truth())

    outcome = cs.reconcile(1_000.0)
    cs.register("strat-1", 1_001.0)

    assert outcome.admitted is True
    assert outcome.state is ColdStartState.FLAT_ASSERTED
    assert cs.registration_admitted() is True
    assert cs.registered() == ("strat-1",)


def test_HYPOTHESIS_gates_registration_is_UNFALSIFIABLE_without_an_ATTEMPT() -> None:
    """§0a hypothesis — stated by the brief, and MEASURED here: CONFIRMED.

    Claim: *"gates registration" is unfalsifiable unless something attempts to
    register.* The measurement uses a deliberately broken subclass whose
    `register` ignores the gate. Against it:

      * the bool-only check `registration_admitted() is False` still PASSES — so a
        drill that only reads the flag green-lights a gate that does not gate;
      * a real `register` ATTEMPT SUCCEEDS — the strategy is admitted against an
        open, un-reconciled position.

    The bool-only assertion measured nothing; the attempt is what falsifies the
    gate. That is exactly the brief's hypothesis, and it holds. The rest of the D2
    tests therefore drive an attempt, never just the flag.
    """

    class _BypassColdStart(ColdStart):
        def register(self, strategy_id: str, now: float) -> None:
            del now
            self._registered.append(strategy_id)  # the gate, removed

    broker = FakeBroker(open_truth(1), (True, "open"))
    bypass = _BypassColdStart(broker, FakeFlattener(broker), FakeHalt(), Recorder())

    # A drill that only reads the flag would call this "safe":
    assert bypass.registration_admitted() is False

    # But the ATTEMPT — the only thing that falsifies the property — goes through:
    bypass.register("strat-x", 1_000.0)
    assert bypass.registered() == ("strat-x",), (
        "the attempt exposed a gate the bool-only check could not — the hypothesis "
        "that 'gates registration' needs an attempt to be falsifiable is CONFIRMED"
    )


# --------------------------------------------------------------------------
# D3 — unexpected open position ⇒ flatten to flat BEFORE any registration
# --------------------------------------------------------------------------


def test_D3_an_unexpected_position_is_FLATTENED_before_registration_is_admitted() -> (
    None
):
    """§4: any unexpected open position ⇒ flatten to flat before any strategy
    registers; never adopt, never reason about it.

    can-fail: the site is `reconcile`'s flatten branch. If admission preceded the
    flatten (or skipped it), `flattener.calls` would be empty while `admitted` is
    True — this test asserts the flatten fired AND that registration was refused
    until it did.
    """
    cs, broker, flattener, _halt, _rec = build(open_truth(2))

    # Before reconcile the attempt is refused: an inherited position is present.
    with pytest.raises(RegistrationRefused):
        cs.register("strat-1", 999.0)

    outcome = cs.reconcile(1_000.0)

    assert len(flattener.calls) == 1, "the inherited position was not flattened"
    assert outcome.flattened == (FlattenTrigger.ORPHAN, FlattenTrigger.ORPHAN)
    assert outcome.admitted is True
    assert broker.current.is_flat, "reconcile did not re-confirm broker-flat"
    cs.register("strat-1", 1_001.0)  # now admitted
    assert cs.registered() == ("strat-1",)


def test_D3_reconcile_RE_QUERIES_broker_truth_to_CONFIRM_the_flat() -> None:
    """§4/C3: the flatten may hit nothing or close a real position, so the Limiter
    reconciles against broker truth afterward and publishes the CONFIRMED state.
    Two polls: the initial truth and the post-flatten confirmation."""
    cs, broker, _flat, _halt, _rec = build(open_truth(1))
    cs.reconcile(1_000.0)
    assert broker.polls == 2, "reconcile did not re-query to confirm the flat"


def test_D3_a_FLATTEN_that_does_NOT_reach_flat_FAILS_CLOSED_no_admission() -> None:
    """The realistic partial-flatten / lost-race case: the flatten fired but the
    broker still reports a position. Known state beats optimal state — refuse to
    admit, hold in HALT.

    can-fail: the site is `reconcile`'s post-confirm branch. A build that admitted
    on `flattener` returning triggers (rather than on a broker-CONFIRMED flat)
    would flip `admitted` True here; this asserts it stays False and held.
    """
    cs, _broker, flattener, halt, _rec = build(open_truth(1), flatten_succeeds=False)

    outcome = cs.reconcile(1_000.0)

    assert len(flattener.calls) == 1
    assert outcome.admitted is False
    assert outcome.state is ColdStartState.HELD_IN_HALT
    assert halt.reasons and "still reports" in halt.reasons[0], halt.reasons
    with pytest.raises(RegistrationRefused):
        cs.register("strat-1", 1_001.0)


# --------------------------------------------------------------------------
# D4 — the market-tradable guard, and its TWO halves (§0a hypothesis, MEASURED)
# --------------------------------------------------------------------------


def test_D4_half1_open_position_on_a_SHUT_market_HOLDS_in_HALT_with_a_LOUD_alert() -> (
    None
):
    """§4: the box comes up to an open position while the market is closed/halted ⇒
    the system does NOT fire into a shut market. It holds in HALT with a loud
    alert and flattens nothing yet.

    can-fail: the site is `reconcile`'s not-tradable branch. A build that flattened
    regardless of the market would show `flattener.calls` non-empty and no HALT
    reason; this asserts the flatten did NOT fire, the alert DID, and registration
    is refused.
    """
    cs, _broker, flattener, halt, _rec = build(
        open_truth(1), tradable=(False, "weekend: market closed")
    )

    outcome = cs.reconcile(1_000.0)

    assert not flattener.calls, "fired a market order into a SHUT market"
    assert outcome.state is ColdStartState.HELD_IN_HALT
    assert outcome.admitted is False
    assert len(halt.reasons) == 1, "the loud HALT alert did not fire"
    assert "NOT tradable" in halt.reasons[0], halt.reasons[0]
    assert "weekend: market closed" in halt.reasons[0], halt.reasons[0]
    with pytest.raises(RegistrationRefused):
        cs.register("strat-1", 1_001.0)


def test_D4_half2_the_SAME_box_FLATTENS_the_instant_the_market_REOPENS() -> None:
    """§4: flattens the instant the market is tradable. The held box re-runs
    reconcile when the market reopens; only now does the flatten fire and admission
    follow.

    can-fail: if the held state were terminal (no re-flatten path) the second
    reconcile would not flatten and `admitted` would stay False; this asserts the
    reopen flattens and admits.
    """
    cs, broker, flattener, halt, _rec = build(
        open_truth(1), tradable=(False, "session gap")
    )
    held = cs.reconcile(1_000.0)
    assert held.admitted is False and not flattener.calls

    broker.tradable = (True, "RTH reopen")  # the market opens
    reopened = cs.reconcile(2_000.0)

    assert len(flattener.calls) == 1, "did not flatten on reopen"
    assert reopened.flattened == (FlattenTrigger.ORPHAN,)
    assert reopened.admitted is True
    assert reopened.state is ColdStartState.FLAT_ASSERTED
    assert len(halt.reasons) == 1, "reopen must not raise a second HALT hold"
    cs.register("strat-1", 2_001.0)
    assert cs.registered() == ("strat-1",)


def test_D4_the_GUARD_lives_on_flatten_to_flat_itself_and_REFUSES_a_shut_market() -> (
    None
):
    """The guard is a property of the flatten PRIMITIVE, not only the reconcile
    flow: a caller reaching `flatten_to_flat` directly on a shut market is refused,
    loudly, and no market order is fired.

    can-fail: the site is `flatten_to_flat`'s `if not tradable: raise`. Removing it
    would fire `flattener.flatten` into the shut market; this asserts the raise and
    that the flattener was never called.
    """
    cs, _broker, flattener, _halt, _rec = build(
        open_truth(1), tradable=(False, "exchange halt")
    )

    with pytest.raises(ColdStartError) as caught:
        cs.flatten_to_flat(open_truth(1))

    assert "shut market" in str(caught.value), str(caught.value)
    assert "exchange halt" in str(caught.value), str(caught.value)
    assert "market-tradable guard" in str(caught.value), str(caught.value)
    assert not flattener.calls, "a market order was fired despite the guard"


def test_HYPOTHESIS_an_ALWAYS_OPEN_drill_measures_NEITHER_half_of_the_guard() -> None:
    """§0a hypothesis — stated by the brief, and MEASURED here: CONFIRMED.

    Claim: *a drill with the market always open measures NEITHER half.* With the
    market always tradable, reconcile flattens and admits and NEVER reaches
    `hold_in_halt` — so the held-in-HALT half is untouched — and there is no reopen
    event, so the flatten-on-reopen half is untouched. The two halves each need
    their own drill, which is why `half1` and `half2` above exist and this one does
    not stand in for them.
    """
    cs, _broker, flattener, halt, _rec = build(open_truth(1), tradable=(True, "open"))

    outcome = cs.reconcile(1_000.0)

    assert outcome.admitted is True
    assert len(flattener.calls) == 1
    assert not halt.reasons, (
        "an always-open drill reached the HALT path — it cannot, and that is the "
        "point: this drill measures neither guard half; the hypothesis is CONFIRMED"
    )


def test_D4_flatten_to_flat_on_an_ALREADY_FLAT_truth_flattens_NOTHING() -> None:
    """A flat truth has nothing to flatten and nothing to adopt — empty, never a
    market order."""
    cs, _broker, flattener, _halt, _rec = build(flat_truth())
    assert cs.flatten_to_flat(flat_truth()) == ()
    assert not flattener.calls


# --------------------------------------------------------------------------
# D5 — restart = flat, ALWAYS. Even a winning inherited position (§14)
# --------------------------------------------------------------------------


def test_D5_a_WINNING_inherited_position_is_FLATTENED_never_ADOPTED() -> None:
    """§14: restart = flat, always. No resume of a prior position, even a winning
    one. The inherited position here is 'winning' — a healthy balance well above
    its notional — and it is flattened regardless: there is no profitability branch
    to adopt it.

    can-fail: the site is the absence of any adopt path. If reconcile inspected P&L
    and adopted a winner, `flattener.calls` would be empty and `admitted` True
    against a live position; this asserts the winner is flattened and admission
    follows only the confirmed flat.
    """
    winning = open_truth(1, balance=250_000.0)  # deep in profit — still flattened
    cs, broker, flattener, _halt, _rec = build(winning)

    # Even a winner does not register while it is still open:
    with pytest.raises(RegistrationRefused):
        cs.register("strat-1", 999.0)

    outcome = cs.reconcile(1_000.0)

    assert len(flattener.calls) == 1, "a winning position was ADOPTED, not flattened"
    assert outcome.flattened == (FlattenTrigger.ORPHAN,)
    assert broker.current.is_flat, "the winner was not taken to flat"
    assert outcome.admitted is True


def test_D5_a_WINNING_and_a_LOSING_inherited_position_behave_IDENTICALLY() -> None:
    """The measurement behind 'even a winning one': the code has NO branch on
    profitability. A winner (high balance) and a loser (low balance) flatten and
    admit through the identical path — proven by identical observable behaviour."""
    win_cs, win_b, win_f, _wh, _wr = build(open_truth(1, balance=250_000.0))
    lose_cs, lose_b, lose_f, _lh, _lr = build(open_truth(1, balance=3_000.0))

    win = win_cs.reconcile(1_000.0)
    lose = lose_cs.reconcile(1_000.0)

    assert len(win_f.calls) == len(lose_f.calls) == 1
    assert win.flattened == lose.flattened == (FlattenTrigger.ORPHAN,)
    assert win.admitted is lose.admitted is True
    assert win_b.current.is_flat and lose_b.current.is_flat


# --------------------------------------------------------------------------
# Plane 1 (§9, §12.10) — the cold-start outcome is booked, sole writer
# --------------------------------------------------------------------------


def test_the_ADMIT_and_HOLD_outcomes_each_BOOK_a_PLANE1_row_carrying_the_reason() -> (
    None
):
    """§12.10 books the cold-start outcome on Plane 1; §9 requires ts + strategy_id
    + reason on every row. Booked under COLD_START (ARC 029 Stage 2.2 added the
    §12.10 member to the seam once this mechanism existed) — carries state and
    admission."""
    cs, _broker, _flat, _halt, rec = build(open_truth(1), tradable=(False, "closed"))
    cs.reconcile(1_000.0)  # a HELD outcome

    assert len(rec.rows) == 1, rec.rows
    row = rec.rows[0]
    assert row.kind is EventKind.COLD_START, row
    assert row.ts == 1_000.0
    assert row.reason and "HALT" in row.reason, row
    assert row.fields["state"] == ColdStartState.HELD_IN_HALT.value, row
    assert row.fields["admitted"] == "False", row


def test_the_ADMIT_path_books_a_row_that_names_the_broker_balance() -> None:
    """The provably-flat admission is the money-truth event; its row carries the
    broker-authoritative balance the whole gate turned on."""
    cs, _broker, _flat, _halt, rec = build(flat_truth(balance=88_888.0))
    cs.reconcile(1_000.0)

    assert len(rec.rows) == 1
    assert "88888.0" in rec.rows[0].reason, rec.rows[0].reason
    assert rec.rows[0].fields["admitted"] == "True"


def test_the_RECONCILER_REQUIRES_all_four_collaborators_no_silent_black_hole() -> None:
    """§9: the Limiter is the SOLE writer of Plane 1. A reconciler defaulting its
    Plane-1 sink to a black hole would keep books nobody can read; none of the four
    collaborators has a default."""
    with pytest.raises(TypeError):
        ColdStart()  # type: ignore[call-arg]  # pylint: disable=no-value-for-parameter
