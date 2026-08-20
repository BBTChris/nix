"""ARC 044 / I2 — every reservation reaches EXACTLY ONE terminal release.

§14:972 locks it; §3:151 names the release set; §15 C1:985 records that the
at-most-one half closed a double-spend race. Both halves are load-bearing and
they fail in opposite directions:

* **AT LEAST ONE.** A terminal path with no release permanently inflates Σ
  reservations, so `committed` never falls and §3 Phase B slowly denies
  everything. ARC 038 / F-B3 measured three of §3's six paths with NO production
  release site at all (CHECK-DEBT D3.358); `scripts/nixrisk/outcomes.py` is the
  repair.
* **AT MOST ONE.** A second release decrements Σ twice, so `committed`
  UNDER-counts and the gate approves against headroom already spent — the cap
  breach §15 C1 closed.

## THE ENUMERATION IS THE PROOF OBLIGATION

The exhaustive drive below does not run over a list of paths typed into this
file. It runs over the set DERIVED from the tree by
`check_reservation_lifecycle.release_sites` — an AST census of every
`resolve`/`release` call in the Limiter's package with its `via` read statically
— intersected with the frozen spec's own parsed path set. A future terminal path
added without a release is exactly the defect I2 exists to forbid, so a proof
over a fixed list would be blind to it by construction.

Two independent censuses exist in this tree (this arc's gate arm, and ARC 038's
ratchet in `test_arc038_b_reservation_terminality.py`). They are cross-checked
against each other here rather than one being deleted: two implementations that
agree is a stronger statement than one nobody can contradict, and drift between
them becomes a failure instead of a silent divergence.

NO retry and NO auto-resend is asserted anywhere in this suite (§4, §2A:71).
"""

from __future__ import annotations

# House pragmas, same set the sibling ARC 038/B suite carries: the SCREAMING
# control names are this tree's convention for naming the property under test,
# the fixtures shadow module-level names by design, and the two censuses are
# compared through one module-private helper on purpose (see that control).
# pylint: disable=invalid-name,protected-access,use-implicit-booleaness-not-comparison
# pylint: disable=missing-function-docstring,too-few-public-methods
# pylint: disable=wrong-import-position,import-error,duplicate-code
import ast
import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "checks"))

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
import check_reservation_lifecycle as gate
from nixrisk import flatten as flatten_mod
from nixrisk.fills import IocRemainder
from nixrisk.outcomes import (
    HANDLES,
    Disposition,
    InvalidOutcomeConfig,
    OrderOutcomes,
)
from nixrisk.reservations import ReservationLedger
from nixrisk.seam import (
    ProposedOrder,
    Side,
    StopMode,
    TerminalPath,
)

_RATCHET_PATH = REPO / "scripts" / "tests" / "test_arc038_b_reservation_terminality.py"


def _ratchet() -> Any:
    """ARC 038's independent census, imported by path (it is not a package)."""
    spec = importlib.util.spec_from_file_location("_arc038b", _RATCHET_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ==========================================================================
# harness — real ledger, real handlers, duck-typed ports only
# ==========================================================================


class Sink:
    """A Plane-1 sink that keeps every row. §9's `enqueue`, no durability."""

    def __init__(self) -> None:
        self.rows: list[Any] = []

    def enqueue(self, row: Any) -> None:
        self.rows.append(row)

    def sync_to_disk(self) -> int:
        return 0

    def pending(self) -> int:
        return 0


class Clock:
    """Monotone, advanced by the drive. Never `time.time`."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = float(start)

    def __call__(self) -> float:
        self.now += 1.0
        return self.now

    def jump(self, seconds: float) -> None:
        self.now += float(seconds)


class Status:
    """What a §4 status query answered. Structural — no vendor type crosses."""

    def __init__(self, state: str) -> None:
        self.state = state
        self.terminal = state in ("cancelled", "rejected", "filled")
        self.cumulative_qty = 0
        self.asked: list[str] = []

    def query_order_status(self, client_order_id: str) -> Status:
        self.asked.append(client_order_id)
        return self


class Broker:
    """§4's IOC cancel, and nothing else. One verb, and it never places."""

    def __init__(self) -> None:
        self.cancelled: list[str] = []

    def cancel_order(self, client_order_id: str) -> None:
        self.cancelled.append(client_order_id)


class Noop:
    """Every port `ProtectiveFlatten` stores but the onset sweep never calls."""

    def __getattr__(self, _name: str) -> Any:
        return lambda *args, **kwargs: None


def order(coid: str, per_contract: float = 3086.25, qty: int = 2) -> ProposedOrder:
    return ProposedOrder(
        client_order_id=coid,
        strategy_id="strat-044",
        symbol="ESZ6",
        side=Side.LONG,
        qty=qty,
        margin_per_contract=per_contract,
        stop_ticks=20,
        stop_mode=StopMode.FIXED,
        signal_ts=1000.0,
    )


def take(ledger: ReservationLedger, clock: Clock, coid: str, **kwargs: Any) -> Any:
    """Take a reservation and PROVE it was taken. Non-vacuity, every time.

    A release measured against a reservation that never existed proves nothing,
    so every drive in this file goes through here and no drive is trusted until
    Σ has been observed to RISE by the exact proposed margin.
    """
    proposal = order(coid, **kwargs)
    before = ledger.total_reserved()
    outstanding_before = len(ledger.outstanding())
    reservation = ledger.take(proposal, clock())
    after = ledger.total_reserved()
    assert after - before == pytest.approx(proposal.proposed_margin), (
        f"NON-VACUITY: Σ went {before} -> {after} on a take of "
        f"{proposal.proposed_margin} — nothing was reserved, so no release "
        "reading below would mean anything"
    )
    assert len(ledger.outstanding()) == outstanding_before + 1
    return proposal, reservation, before


# ==========================================================================
# S3a — the derived set, and its completeness
# ==========================================================================


def derived_paths() -> dict[str, list[str]]:
    """The production release-site census, BY SHAPE, from the gate's own arm."""
    return gate.release_sites(REPO)


def spec_paths() -> tuple[str, ...]:
    parsed, complaint = gate.spec_paths(REPO)
    assert complaint == "", complaint
    return parsed


def test_the_DERIVED_terminal_path_set_is_COMPLETE_and_has_no_unreadable_site() -> None:
    """The completeness obligation: nothing in the tree ends a reservation unseen.

    An unreadable `via` is the failure this asserts against. The census reports
    such a call under a bucket of its own precisely so it cannot be credited to
    nothing, and a terminal-transition site nobody can name is a path that might
    leak with no instrument able to say. That case must be CANNOT_MEASURE in the
    gate and a FAILURE here — never a quiet pass.
    """
    sites = derived_paths()

    assert gate.UNREADABLE not in sites, (
        f"a release call whose terminal path cannot be read statically: "
        f"{sites.get(gate.UNREADABLE)} — the enumeration below would be "
        "incomplete and this suite would be proving a property over a subset it "
        "cannot describe"
    )
    declared = {member.name for member in TerminalPath}
    wired = set(sites)
    assert wired <= declared, f"a release booked under a non-member: {wired - declared}"
    missing = set(spec_paths()) - wired
    assert not missing, (
        f"§3 names {sorted(missing)} as release path(s) and no production module "
        "books them — §14's AT-LEAST-ONE half, the D3.358 defect"
    )


def test_the_TWO_INDEPENDENT_censuses_agree() -> None:
    """The gate's arm and ARC 038's ratchet must see the same tree the same way."""
    mine = {member: sorted(sites) for member, sites in derived_paths().items()}
    ratchet_census = _ratchet()._release_sites  # pylint: disable=protected-access
    theirs = {
        member: sorted(sites)
        for member, sites in ratchet_census(REPO / "scripts" / "nixrisk").items()
    }

    assert mine == theirs, (
        f"two censuses of one tree disagree — gate={mine} ratchet={theirs}. One "
        "of them is reading the wiring wrongly and neither can be trusted until "
        "they are reconciled"
    )


# ==========================================================================
# S3a — EXHAUSTIVE: drive EVERY derived path, each releases exactly once
# ==========================================================================


def drive_fill(clock: Clock, ledger: ReservationLedger, coid: str) -> None:
    """FILL — `fills.py::IocRemainder`, the shipped production release site."""
    remainder = IocRemainder(reservations=ledger, cancels=Broker(), clock=clock)
    remainder.release_remainder(coid, filled_qty=1, requested_qty=2)


def drive_onset(cause: TerminalPath) -> Any:
    """BLACKOUT_ONSET / HALT_ONSET — `flatten.py::cancel_entries_on_onset`."""

    def run(clock: Clock, ledger: ReservationLedger, coid: str) -> None:
        sweep = flatten_mod.ProtectiveFlatten(
            broker=Broker(),  # type: ignore[arg-type]
            ledger=ledger,
            picture=Noop(),  # type: ignore[arg-type]  # type: ignore[arg-type]
            strategy=Noop(),
            plane1=Sink(),
            scoring=Noop(),
            clock=clock,
        )
        result = sweep.cancel_entries_on_onset(
            cause, [flatten_mod.PendingEntry(coid, "strat-044", "ESZ6")]
        )
        assert len(result.released) == 1, result

    return run


def drive_outcome(member: str) -> Any:
    """The three non-fill paths — `outcomes.py::OrderOutcomes`, ARC 044."""

    def run(clock: Clock, ledger: ReservationLedger, coid: str) -> None:
        handler = OrderOutcomes(ledger, clock=clock, pending_ack_timeout_s=2.0)
        verb = {path.name: name for path, name in HANDLES.items()}[member]
        method = getattr(handler, verb)
        if verb == "resolve_pending_timeouts":
            clock.jump(10.0)
            records = method(Status("cancelled"))
            assert len(records) == 1, records
            assert records[0].disposition is Disposition.RELEASED, records
        else:
            assert method(coid).disposition is Disposition.RELEASED

    return run


#: How each DERIVED path is reached in production. Keyed by the path, so a path
#: the census finds and this table does not cover is a hard failure below — the
#: table can never silently shrink the drive.
DRIVERS = {
    "FILL": drive_fill,
    "BLACKOUT_ONSET": drive_onset(TerminalPath.BLACKOUT_ONSET),
    "HALT_ONSET": drive_onset(TerminalPath.HALT_ONSET),
    "CANCEL": drive_outcome("CANCEL"),
    "REJECT": drive_outcome("REJECT"),
    "PENDING_TIMEOUT": drive_outcome("PENDING_TIMEOUT"),
}


def _parametrised_rosters() -> list[list[str]]:
    """Every `parametrize` roster spelled in THIS file, read from its own AST.

    The per-path controls below carry their roster as an INLINE LITERAL, twice.
    That is deliberate on both counts:

    1. `checks/check_derived_claims.py` counts this tree's tests statically and
       REFUSES a `parametrize` whose argvalues it cannot read; a computed
       sequence turns the whole test census into CANNOT_MEASURE. A derivation
       that blinds the instrument counting it is not worth the derivation.
    2. A literal roster is only honest if something compares it to reality — so
       this function reads the rosters back out of the file's own source and the
       test below asserts each one EQUALS the set derived from the tree. The
       literal therefore cannot silently shrink: a path that gains a production
       release site fails until the decorators move, and a path that loses one
       fails as the leak. The same one-way ratchet ARC 038's `WIRED_PATHS` is.
    """
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    rosters: list[list[str]] = []
    for node in ast.walk(tree):
        for deco in getattr(node, "decorator_list", []):
            if not isinstance(deco, ast.Call):
                continue
            if "parametrize" not in ast.unparse(deco.func):
                continue
            values = deco.args[1] if len(deco.args) > 1 else None
            assert isinstance(values, (ast.List, ast.Tuple)), ast.unparse(deco)
            rosters.append([ast.literal_eval(element) for element in values.elts])
    return rosters


def test_the_DRIVEN_SET_equals_the_DERIVED_SET() -> None:
    """No path the tree books may go undriven, and none may be invented here."""
    derived = set(derived_paths()) - {gate.UNREADABLE}

    assert set(DRIVERS) == derived, (
        f"this suite drives {sorted(DRIVERS)} and the tree books {sorted(derived)}"
        " — a path booked in production with no drive here is precisely the "
        "unlisted future path §14 exists to forbid"
    )
    rosters = _parametrised_rosters()
    assert rosters, "no parametrised roster found — the per-path controls vanished"
    for roster in rosters:
        assert len(roster) == len(set(roster)), roster
        assert set(roster) == derived, (
            f"a parametrised roster {sorted(roster)} is not the set the tree "
            f"books {sorted(derived)} — those controls would be running over a "
            "roster nobody re-derived"
        )


@pytest.mark.parametrize(
    "member",
    ("BLACKOUT_ONSET", "CANCEL", "FILL", "HALT_ONSET", "PENDING_TIMEOUT", "REJECT"),
)
def test_EVERY_derived_terminal_path_releases_EXACTLY_ONCE(member: str) -> None:
    """§14, exhaustively: Σ back to baseline, one RELEASED record, store empty."""
    clock = Clock()
    ledger = ReservationLedger(Sink())
    coid = f"c-{member.lower()}"
    proposal, reservation, baseline = take(ledger, clock, coid)
    taken = ledger.total_reserved()

    DRIVERS[member](clock, ledger, coid)

    assert ledger.total_reserved() == baseline, (
        f"{member}: Σ went {taken} -> {ledger.total_reserved()} against a "
        f"baseline of {baseline} — the {proposal.proposed_margin} this order "
        "reserved was not returned. A LEAK: committed margin stays inflated"
    )
    assert ledger.outstanding() == (), ledger.outstanding()
    released = ledger.released()
    assert len(released) == 1, released
    assert released[0].reservation_id == reservation.reservation_id
    assert released[0].released_via is getattr(TerminalPath, member), released[0]
    audit = ledger.audit()
    assert audit.released == 1 and audit.taken == 1, audit
    assert not audit.material, audit


@pytest.mark.parametrize(
    "member",
    ("BLACKOUT_ONSET", "CANCEL", "FILL", "HALT_ONSET", "PENDING_TIMEOUT", "REJECT"),
)
def test_a_SECOND_terminal_event_on_ANY_path_is_a_RECORDED_NO_OP(member: str) -> None:
    """The at-most-one half, on every derived path, watched past the event.

    The second event must not move Σ by a single bit, must not add a RELEASED
    record, and must be visible — a silently swallowed duplicate is a defect
    nobody can audit even when the arithmetic survives it.
    """
    clock = Clock()
    ledger = ReservationLedger(Sink())
    coid = f"c-{member.lower()}"
    _proposal, _reservation, baseline = take(ledger, clock, coid)
    DRIVERS[member](clock, ledger, coid)
    after = ledger.total_reserved()
    refusals_before = len(ledger.refusals())

    # Every path's SECOND event, in the shape the ledger's own event surface
    # takes it — the two production verbs are `resolve` (order-keyed) and
    # `release` (id-keyed), and both are exercised.
    second = ledger.resolve(coid, getattr(TerminalPath, member), clock())

    assert ledger.total_reserved() == after, (
        f"{member}: a second terminal event moved Σ {after} -> "
        f"{ledger.total_reserved()} — a DOUBLE RELEASE. committed UNDER-counts "
        "and §3 Phase B approves against headroom already spent (§15 C1)"
    )
    assert after == baseline
    assert second.released is None and second.refusal is not None, second
    assert len(ledger.released()) == 1, ledger.released()
    assert len(ledger.refusals()) == refusals_before + 1, ledger.refusals()
    assert "exactly one terminal release" in second.refusal.reason, second.refusal


# ==========================================================================
# S3b — NO DOUBLE RELEASE UNDER RACE
# ==========================================================================


def test_a_PARTIAL_FILL_REMAINDER_arriving_after_a_CANCEL_releases_only_once() -> None:
    """§4's cancel-loses-the-race: the remainder fills after the cancel landed.

    Order of arrival is the whole point. The cancel is confirmed first and
    releases; the fill for the part that got done arrives afterwards and must be
    REFUSED, not absorbed as a second decrement. Σ is compared BIT-identically,
    because `-= margin` and `= saved` do not return to the same bits and the
    difference is exactly the drift §11.7 watches for.
    """
    clock = Clock()
    ledger = ReservationLedger(Sink())
    _proposal, _reservation, baseline = take(ledger, clock, "c-race-1")
    handler = OrderOutcomes(ledger, clock=clock, pending_ack_timeout_s=2.0)
    broker = Broker()
    remainder = IocRemainder(reservations=ledger, cancels=broker, clock=clock)

    cancelled = handler.on_cancel("c-race-1")
    after_cancel = ledger.total_reserved()
    sigma_from_fill = remainder.release_remainder(
        "c-race-1", filled_qty=1, requested_qty=2
    )

    assert cancelled.disposition is Disposition.RELEASED, cancelled
    assert after_cancel == baseline
    assert sigma_from_fill == after_cancel, (
        "the late partial fill moved Σ after the cancel already released it"
    )
    assert ledger.total_reserved() == baseline
    assert len(ledger.released()) == 1, ledger.released()
    assert ledger.released()[0].released_via is TerminalPath.CANCEL
    assert remainder.refused_releases == 1, remainder.refused_releases
    assert broker.cancelled == ["c-race-1"], broker.cancelled


def test_a_PENDING_TIMEOUT_then_TERMINAL_FEEDBACK_releases_only_once() -> None:
    """The timeout-vs-feedback race, in both orders, on two fresh reservations."""
    for first_is_timeout in (True, False):
        clock = Clock()
        ledger = ReservationLedger(Sink())
        _proposal, _reservation, baseline = take(ledger, clock, "c-race-2")
        handler = OrderOutcomes(ledger, clock=clock, pending_ack_timeout_s=2.0)
        clock.jump(10.0)
        status = Status("cancelled")

        if first_is_timeout:
            first = handler.resolve_pending_timeouts(status)[0]
            second = handler.on_reject("c-race-2")
        else:
            first = handler.on_reject("c-race-2")
            second_records = handler.resolve_pending_timeouts(status)
            # The sweep reads the ledger's own TAKEN set, so a reservation
            # already released is not even due: no query is issued for it.
            assert second_records == (), second_records
            second = None

        assert first.disposition is Disposition.RELEASED, first
        assert ledger.total_reserved() == baseline
        assert len(ledger.released()) == 1, ledger.released()
        if second is not None:
            assert second.disposition is Disposition.REFUSED, second
            assert second.sigma_before == second.sigma_after == baseline
            assert handler.refused == 1
        assert not ledger.audit().material, ledger.audit()


def test_a_BLACKOUT_ONSET_during_a_PENDING_order_releases_only_once() -> None:
    """Onset cancels the pending entry; the timeout sweep must not release again.

    The onset books its OWN cause (SPEC-A7) and the later pending-timeout
    resolution must neither re-release nor re-cause: a second event that landed
    would both under-count committed and overwrite which onset returned the
    capital in §9's record of money truth.
    """
    clock = Clock()
    ledger = ReservationLedger(Sink())
    _proposal, _reservation, baseline = take(ledger, clock, "c-race-3")
    handler = OrderOutcomes(ledger, clock=clock, pending_ack_timeout_s=2.0)
    sweep = flatten_mod.ProtectiveFlatten(
        broker=Broker(),  # type: ignore[arg-type]
        ledger=ledger,
        picture=Noop(),  # type: ignore[arg-type]
        strategy=Noop(),
        plane1=Sink(),
        scoring=Noop(),
        clock=clock,
    )

    onset = sweep.cancel_entries_on_onset(
        TerminalPath.BLACKOUT_ONSET,
        [flatten_mod.PendingEntry("c-race-3", "strat-044", "ESZ6")],
    )
    after_onset = ledger.total_reserved()
    clock.jump(30.0)
    status = Status("cancelled")
    late = handler.resolve_pending_timeouts(status)
    # And the explicit feedback that could still arrive from the venue.
    late_reject = handler.on_reject("c-race-3")

    assert len(onset.released) == 1, onset
    assert after_onset == baseline
    assert late == (), late
    assert status.asked == [], status.asked
    assert late_reject.disposition is Disposition.REFUSED, late_reject
    assert ledger.total_reserved() == baseline
    assert len(ledger.released()) == 1, ledger.released()
    assert ledger.released()[0].released_via is TerminalPath.BLACKOUT_ONSET
    assert not ledger.audit().material, ledger.audit()


# ==========================================================================
# the handler's own refusals — the safe direction, and the config guard
# ==========================================================================


def test_a_STILL_WORKING_order_is_NOT_released_by_the_timeout_sweep() -> None:
    """§4 resolves a timeout by QUERYING; a live order keeps its commitment.

    The opposite choice is the cap breach: freeing margin for an order that is
    still working at the venue under-counts committed while a real commitment
    stands. `flatten.py` records the same decision at its own refusal site.
    """
    for state in ("working", "indeterminate", "unknown", "filled"):
        clock = Clock()
        ledger = ReservationLedger(Sink())
        _proposal, _reservation, _baseline = take(ledger, clock, "c-live")
        taken = ledger.total_reserved()
        handler = OrderOutcomes(ledger, clock=clock, pending_ack_timeout_s=2.0)
        clock.jump(10.0)

        records = handler.resolve_pending_timeouts(Status(state))

        assert len(records) == 1, (state, records)
        assert records[0].disposition is Disposition.HELD, (state, records[0])
        assert ledger.total_reserved() == taken, state
        assert len(ledger.outstanding()) == 1, state
        assert ledger.released() == (), state
        assert handler.held == 1 and handler.timeouts_released == 0, state


def test_an_UNKNOWN_VENUE_STATE_is_HELD_and_never_guessed() -> None:
    """A state outside the seam's declared set is not evidence of death."""
    clock = Clock()
    ledger = ReservationLedger(Sink())
    take(ledger, clock, "c-weird")
    taken = ledger.total_reserved()
    handler = OrderOutcomes(ledger, clock=clock, pending_ack_timeout_s=2.0)
    clock.jump(10.0)

    records = handler.resolve_pending_timeouts(Status("partially_filled_maybe"))

    assert records[0].disposition is Disposition.HELD, records
    assert "outside the seam's declared set" in records[0].detail
    assert ledger.total_reserved() == taken


def test_the_TIMEOUT_KNOB_is_BOOT_VALIDATED_and_refuses_a_degenerate_value() -> None:
    """§12A:801-802 — an invalid tunable is rejected, not absorbed at run time."""
    ledger = ReservationLedger(Sink())
    for bad in (0.0, -1.0, float("nan"), float("inf")):
        with pytest.raises(InvalidOutcomeConfig) as caught:
            OrderOutcomes(ledger, clock=Clock(), pending_ack_timeout_s=bad)
        assert "PENDING_ACK_TIMEOUT_MS" in str(caught.value), caught.value


def test_the_MODULE_holds_NO_RETRY_and_NO_RESEND_verb() -> None:
    """§4 / §2A:71 — the only outbound verb this module has is a status QUERY.

    Asserted over the module's CALL GRAPH, not over its text. A grep would match
    the paragraph in its own docstring that explains why it never resends, and a
    control that reddens on its own subject's prose is measuring the prose.
    """
    tree = ast.parse(
        (REPO / "scripts" / "nixrisk" / "outcomes.py").read_text(encoding="utf-8")
    )
    called = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }

    forbidden = called & {"place_order", "flatten", "resend", "retry", "send_order"}
    assert not forbidden, (
        f"the non-fill outcome handler calls {sorted(forbidden)} — a release "
        "path that can place, resend or flatten is a second order-placement "
        "site (§4, §2A:71: status query, NEVER an auto-resend)"
    )
    assert "query_order_status" in called, (
        "the module no longer issues §4's status query, so its pending-timeout "
        "resolution is not resolving anything"
    )
