"""ARC 038 / sub-agent A — the can-fail controls for the GATE WALL findings.

§7.12's standing question, asked of THIS file: *what would have to be true for
these controls to pass while measuring nothing?*

Six answers, and each is why the corresponding test is shaped the way it is:

 1. **The plant never loads.** A gate driven against a STAGED, PLANTED copy of the
    tree can silently import the PRODUCTION module instead (D3.344, ARC 037 — two
    suites called `subprocess.run` with no `env=`). Every staged drive here asserts
    the loaded module's `__file__` is under `tmp_path` BEFORE it believes any
    verdict, and the drives are in-process through `check_limiter_gate.run`, which
    purges `sys.modules['nixrisk*']` and re-imports from `ctx.nix_home` — so there
    is no child to inherit a `PYTHONPATH` at all.
 2. **Only the protected half runs.** A control that never sees the bad outcome
    proves nothing (ARC 035, three times). Every behavioural test below runs the
    UNPROTECTED half first and REQUIRES the violation to appear, then the
    protected half and requires it gone.
 3. **The assertion is the exit code.** Check contract v2 §11: every control here
    asserts the REASON — the site, the rule name, or the message — never a bare
    status.
 4. **The subject is a double.** The broker is `broker_seam.StubBrokerOrder`, the
    tree's own vendorless conformance subject, with a REAL working-order book, a
    real `cancel_order` that removes from it, and `simulate_fill`, which raises
    `KeyError` on an order that is no longer working. "The order was cancelled" is
    therefore observed as "it can no longer fill", not asserted off a call log.
 5. **The window is a fixture.** The blackout drive uses the real
    `SessionWindowSource` over the real vendored CME calendar, so the onset
    instant is a real EOD edge and not a number chosen to make an edge happen.
 6. **The enumeration is a list someone typed.** `debug.md` §8 failure mode #14.
    The order-verb roster is DERIVED from `broker_seam.ORDER_PORT_VERBS` minus the
    read-only verbs, and the reach set is derived by parsing every `.py` under
    `scripts/`, with the parse count asserted so a file skipped for a `SyntaxError`
    cannot silently shrink the scope.

Findings under control: FA-1 (`gate.py` partition), FA-2 (`blackout.py` onset
never cancelled at the venue), FA-3 (`flatten.py` / `halt.py` sweep aborted by one
refusal), FA-4 (`gate.py` accepted a degenerate proposal), FA-5 (the I1 reach set).
Every `§` cites `docs/nics_risk_subsystem_spec_v1.3.md`.
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# pylint: disable=wrong-import-position,too-few-public-methods,too-many-lines
# pylint: disable=too-many-boolean-expressions
# Test names SHOUT the property; the sys.path bootstrap is identical in every
# check-driving suite in this tree by requirement, and C0413 is the price of it —
# `sys.path` must carry `scripts/` and `checks/` before the subject can be
# imported at all. R0903: every class here is a PORT DOUBLE with exactly the
# verbs its Protocol declares; a second method would be a double doing two jobs.
# C0302: the overflow is the §7.12 docstring plus the both-halves structure —
# each behavioural control carries its own unprotected half, which is twice the
# code of a control that only ever proves the good outcome, and that doubling is
# the point (ARC 035). R0916: the six-term `if` in `_reach` is the `getattr`
# shape, and every term narrows it — splitting it would spread one pattern match
# over two nested branches.

from __future__ import annotations

import ast
import asyncio
import datetime as dt
import hashlib
import os
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
# APPENDED, never inserted at the front — loader.py's failure mode #8 note.
sys.path.append(str(REPO / "checks"))

import check_limiter_gate as gate_check  # pylint: disable=wrong-import-position
from broker.broker_seam import (  # pylint: disable=wrong-import-position
    ORDER_PORT_VERBS,
    BrokerNotConnected,
    NeutralOrder,
    OrderType,
    RecordingSink,
    StubBrokerOrder,
    TimeInForce,
)
from broker.broker_seam import (
    Side as BrokerSide,  # pylint: disable=wrong-import-position
)
from nixrisk import blackout as bl  # pylint: disable=wrong-import-position
from nixrisk import flatten as fl  # pylint: disable=wrong-import-position
from nixrisk import gate as g  # pylint: disable=wrong-import-position
from nixrisk import halt as hl  # pylint: disable=wrong-import-position
from nixrisk.calendar_seam import (  # pylint: disable=wrong-import-position
    CacheState,
    FreshnessStamp,
)
from nixrisk.reservations import (
    ReservationLedger,  # pylint: disable=wrong-import-position
)
from nixrisk.seam import (  # pylint: disable=wrong-import-position
    Decision,
    EventKind,
    FinancialPicture,
    Phase,
    ProposedOrder,
    Side,
    StopMode,
    TerminalPath,
)
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)

SYMBOL = "ES"  # in the vendored CME calendar's product map; "MES" is not
UTC = dt.UTC


# ---------------------------------------------------------------------------
# Doubles — each carries exactly the port's verbs
# ---------------------------------------------------------------------------


class _Plane1:
    """`Plane1Port`, recording. `enqueue` only; §9's fsync is the pool writer's."""

    def __init__(self) -> None:
        self.rows: list[Any] = []

    def enqueue(self, row: Any) -> None:
        """Append one §12.10 row."""
        self.rows.append(row)

    def sync_to_disk(self) -> int:
        """Never called on the hot path."""
        return 0

    def pending(self) -> int:
        """Depth."""
        return len(self.rows)

    def of(self, kind: Any) -> list[Any]:
        """Every row of one `EventKind`."""
        return [row for row in self.rows if row.kind is kind]


class _Plane2:
    """`Plane2Port`. WRITE-ONLY by contract (§12.10:740)."""

    def __init__(self) -> None:
        self.lines: list[tuple[str, dict[str, Any]]] = []

    def emit(self, event: str, **fields: Any) -> str:
        """One structured operational line."""
        self.lines.append((event, fields))
        return event


class _Clear:
    """A HALT port that never halts, and the §11.1 caches, unblocked."""

    def is_set(self) -> tuple[bool, str]:
        """`(halted, why)`."""
        return (False, "")

    def read(self, symbol: str | None = None) -> tuple[bool, str]:
        """`(blocked, reason)` for a symbol cache or a global one."""
        del symbol
        return (False, "")

    def in_flight(self, strategy_id: str) -> tuple[bool, str]:
        """`(locked, reason)`."""
        del strategy_id
        return (False, "")

    def mark(self) -> tuple[float, bool]:
        """A comfortable, FRESH net-liq mark."""
        return (1e9, True)


def _picture(reservations: float = 0.0) -> FinancialPicture:
    port = _Clear()
    del port
    return FinancialPicture(
        version=1,
        published_ts=0.0,
        balance=100_000.0,
        positions=(),
        margin_per_contract={SYMBOL: 1_000.0},
        sum_open_margin=0.0,
        sum_reservations=reservations,
        committed=reservations,
        deployable=70_000.0 - reservations,
    )


def _proposal(qty: int = 2, coid: str = "c-1", mpc: float = 1_000.0) -> ProposedOrder:
    return ProposedOrder(
        client_order_id=coid,
        strategy_id="s1",
        symbol=SYMBOL,
        side=Side.LONG,
        qty=qty,
        margin_per_contract=mpc,
        stop_ticks=10,
        stop_mode=StopMode.FIXED,
        signal_ts=0.0,
    )


def _manifest() -> tuple[Any, ...]:
    port = _Clear()
    return g.default_manifest(
        blackout=port,
        tradability=port,
        staleness=port,
        clock_skew=port,
        in_flight=port,
        net_liq=port,
        deployable_fraction=0.70,
        survival_safety_pad=0.10,
        coherence_tolerance=0.01,
    )


FLOORS = {cause.value: 60.0 for cause in hl.HaltCause if cause.auto_clearable}


# ===========================================================================
# FA-1 — the partition dispatches EVERY rule EXACTLY ONCE
# ===========================================================================

#: The pre-repair partition, verbatim, as the PLANT. Keyed to the source because
#: that is what a plant is; if `gate.py` moves these lines the plant asserts and
#: this control fails LOUDLY rather than silently matching nothing (D3.189).
_PARTITION_NOW = """        declared = self._validate(halt, rules)
        self._phase_a = tuple(
            rule
            for rule, phase in zip(rules, declared, strict=True)
            if phase is Phase.SIZE_INDEPENDENT
        )
        self._phase_b = tuple(
            rule
            for rule, phase in zip(rules, declared, strict=True)
            if phase is Phase.SIZE_DEPENDENT
        )"""

_PARTITION_PRE_REPAIR = """        self._validate(halt, rules)
        self._phase_a = tuple(r for r in rules if r.phase is Phase.SIZE_INDEPENDENT)
        self._phase_b = tuple(r for r in rules if r.phase is Phase.SIZE_DEPENDENT)"""


@pytest.fixture
def staged(tmp_path: Path) -> Path:
    """A throwaway `nix_home` carrying a COPY of the real `scripts/nixrisk/`."""
    shutil.copytree(REPO / "scripts" / "nixrisk", tmp_path / "scripts" / "nixrisk")
    return tmp_path


def _assert_loaded_from(home: Path) -> None:
    """The staged copy is what got imported — NOT the production tree (D3.344)."""
    subject, complaint = gate_check.load_subject(home)
    assert not complaint and subject is not None, complaint
    loaded = Path(subject.gate.__file__).resolve()
    assert loaded.is_relative_to(home.resolve()), (
        f"the drive imported {loaded}, which is NOT under the staged tree {home} — "
        "every plant below would have been defeated and the verdict would be about "
        "the production module (D3.344)"
    )


def test_the_PARTITION_dispatches_EVERY_rule_EXACTLY_ONCE(staged: Path) -> None:
    """FA-1. `RulePort.phase` is a PROPERTY; re-reading it loses or duplicates rules.

    BOTH HALVES. The unprotected half restores the pre-repair three-read partition
    into the staged copy and REQUIRES `check_limiter_gate` to go red naming the
    partition site; the protected half restores the shipped source byte-identically
    and requires green.
    """
    subject_path = staged / gate_check.GATE
    pristine = subject_path.read_text(encoding="utf-8")
    before = hashlib.sha256(pristine.encode()).hexdigest()
    assert _PARTITION_NOW in pristine, (
        "the partition this control plants against is not in gate.py — the plant "
        "would match nothing and the green below would prove nothing"
    )
    _assert_loaded_from(staged)

    # -- UNPROTECTED HALF: the defect restored --------------------------------
    subject_path.write_text(
        pristine.replace(_PARTITION_NOW, _PARTITION_PRE_REPAIR, 1), encoding="utf-8"
    )
    _assert_loaded_from(staged)
    red = gate_check.run(Mode.VERIFY, Context(nix_home=staged, mode=Mode.VERIFY))
    assert red.status is Status.FAIL_NEEDS_OPERATOR, red
    assert gate_check.PARTITION_SITE in red.site, red.site
    assert "were handed to GatePass" in red.detail, red.detail
    assert "DROPPED=" in red.detail or "DUPLICATED=" in red.detail, red.detail
    assert "phase_flipper" in red.detail, red.detail

    # -- PROTECTED HALF: byte-identical restore -------------------------------
    subject_path.write_text(pristine, encoding="utf-8")
    assert hashlib.sha256(subject_path.read_bytes()).hexdigest() == before
    green = gate_check.run(Mode.VERIFY, Context(nix_home=staged, mode=Mode.VERIFY))
    assert green.status is Status.PASS, green
    assert "phase-A" in green.evidence and "phase-B" in green.evidence, green.evidence


def test_a_PHASE_THAT_FLIPS_is_dispatched_ONCE_by_the_SHIPPED_executor() -> None:
    """FA-1, against the real module rather than a staged copy.

    A DENYING rule that flips its declared phase must still run, and run once, so
    the pass must DENY under its name. Before the repair the same rule was dropped
    and the pass APPROVED.
    """
    A, B = Phase.SIZE_INDEPENDENT, Phase.SIZE_DEPENDENT

    class _Flip:
        """Valid on every read; not the SAME on every read."""

        def __init__(self, sequence: tuple[Phase, ...]) -> None:
            self._sequence = sequence
            self._reads = 0
            self.runs = 0

        @property
        def name(self) -> str:
            """Identifier."""
            return "flipper"

        @property
        def phase(self) -> Phase:
            """A different valid member on successive reads."""
            self._reads += 1
            return self._sequence[min(self._reads - 1, len(self._sequence) - 1)]

        def evaluate(self, order: Any, picture: Any) -> Any:
            """DENY, and count the dispatch."""
            del order, picture
            self.runs += 1
            return g.RuleVerdict(
                rule="flipper", decision=Decision.DENY, reason="flipper denies"
            )

    for sequence in ((A, B, A, B, A), (A, A, B, A, B)):
        flipper = _Flip(sequence)
        handed = [*_manifest(), flipper]
        passer = g.GatePass(_Clear(), handed)
        assert len(passer.manifest) == len(handed), (
            f"{len(handed)} rules handed in, {len(passer.manifest)} partitioned: "
            f"{passer.manifest}"
        )
        outcome = passer.evaluate(_proposal(), _picture(), 0.0)
        assert outcome.decision is Decision.DENY, outcome
        assert outcome.rule == "flipper", outcome
        assert flipper.runs == 1, f"dispatched {flipper.runs} time(s) in one pass"
        assert tuple(outcome.evaluated).count("flipper") == 1, outcome.evaluated


# ===========================================================================
# FA-4 — a degenerate proposal is DENIED by the gate, not by the ledger
# ===========================================================================


@pytest.mark.parametrize("qty", [0, -5])
def test_a_NON_POSITIVE_QUANTITY_is_DENIED_by_the_gate_and_NOT_by_the_ledger(
    qty: int,
) -> None:
    """FA-4. §3:131 'size 0 ⇒ deny', asserted at the authoritative pass (§3:118).

    BOTH HALVES. The unprotected half is the MANIFEST — every rule in the shipped
    manifest is asked directly and must APPROVE the degenerate proposal, which is
    the measurement that nothing else in the pass would have caught it. The
    protected half is the real `GatePass.evaluate`, which must DENY under
    `PROPOSAL_RULE`.
    """
    order = _proposal(qty=qty, coid=f"c-q{qty}")
    snapshot = _picture()

    # -- UNPROTECTED HALF: no rule objects --------------------------------
    approving = [
        rule.name
        for rule in _manifest()
        if rule.evaluate(order, snapshot).decision is Decision.APPROVE
    ]
    assert len(approving) == len(_manifest()), (
        "some rule already denies this proposal, so the pre-gate branch is not the "
        f"only thing standing between it and an approval: {approving}"
    )

    # -- PROTECTED HALF: the real pass -----------------------------------
    outcome = g.GatePass(_Clear(), list(_manifest())).evaluate(order, snapshot, 0.0)
    assert outcome.decision is Decision.DENY, outcome
    assert outcome.rule == g.PROPOSAL_RULE, (
        f"denied under {outcome.rule!r}; §3 requires the BLOCKING branch named, and "
        "'reservation_ledger' names the persistence layer for a fault in the proposal"
    )
    assert "size 0 ⇒ deny" in outcome.reason, outcome.reason
    assert g.PROPOSAL_RULE in outcome.evaluated, outcome.evaluated
    assert outcome.evaluated[0] == g.HALT_RULE, (
        f"§11.5's HALT read must still be first on every pass: {outcome.evaluated}"
    )
    assert outcome.reservation_id is None, "a denied proposal must reserve nothing"


def test_a_NON_FINITE_MARGIN_PER_CONTRACT_is_DENIED_rather_than_silently_passing() -> (
    None
):
    """FA-4. A NaN margin turns every Phase-B `<` into False, which reads as room."""
    order = _proposal(coid="c-nan", mpc=float("nan"))
    outcome = g.GatePass(_Clear(), list(_manifest())).evaluate(order, _picture(), 0.0)
    assert outcome.decision is Decision.DENY, outcome
    assert outcome.rule == g.PROPOSAL_RULE, outcome
    assert "not a usable figure" in outcome.reason, outcome.reason


def test_a_CLAMP_TO_ZERO_is_refused_as_an_approval() -> None:
    """FA-4. §5 makes size-down DISTINCT from deny; a clamp to zero is a deny."""

    class _ClampsToZero:
        """A Phase-B rule returning SIZE_DOWN with `sized_qty=0`."""

        @property
        def name(self) -> str:
            """Identifier."""
            return "clamps_to_zero"

        @property
        def phase(self) -> Phase:
            """Size-dependent."""
            return Phase.SIZE_DEPENDENT

        def evaluate(self, order: Any, picture: Any) -> Any:
            """Clamp to nothing."""
            del order, picture
            return g.RuleVerdict(
                rule="clamps_to_zero",
                decision=Decision.SIZE_DOWN,
                reason="clamped to nothing",
                sized_qty=0,
            )

    passer = g.GatePass(_Clear(), [*_manifest(), _ClampsToZero()])
    outcome = passer.evaluate(_proposal(qty=4, coid="c-zeroclamp"), _picture(), 0.0)
    assert outcome.decision is Decision.DENY, outcome
    assert outcome.rule == "clamps_to_zero", outcome
    assert "SENDABLE" in outcome.reason, outcome.reason


# ===========================================================================
# FA-2 — a BLACKOUT onset cancels the working ENTRY at the venue
# ===========================================================================


class _WindowCache:
    """`WindowSetReadPort` over one real `WindowSet`."""

    def __init__(self, window_set: Any) -> None:
        self._set = window_set

    def windows(self, symbol: str) -> Any:
        """The set for one symbol."""
        del symbol
        return self._set

    def state(self) -> CacheState:
        """FRESH."""
        return CacheState.FRESH

    def freshness(self) -> FreshnessStamp:
        """A stamp inside the threshold."""
        return FreshnessStamp(
            feed="calendar", as_of=dt.datetime(2026, 1, 1, tzinfo=UTC)
        )


class _BaselineCache:
    """`MarginBaselineReadPort` with no baseline — the window arm decides."""

    def baseline(self, symbol: str) -> None:
        """No baseline. §6.3 abstains and the window arm decides."""
        del symbol

    def state(self) -> CacheState:
        """FRESH."""
        return CacheState.FRESH

    def freshness(self) -> FreshnessStamp:
        """A stamp."""
        return FreshnessStamp(feed="margin", as_of=dt.datetime(2026, 1, 1, tzinfo=UTC))


class _PictureRead:
    """`FinancialPicturePort`. The evaluator must never publish (§6.4 read-only)."""

    def publish(self, picture: Any) -> None:
        """Refused."""
        raise AssertionError("the evaluator must never publish (§6.4 read-only)")

    def current(self) -> FinancialPicture:
        """One snapshot."""
        return _picture()


class _Onsets:
    """`OnsetSink`, recording."""

    def __init__(self) -> None:
        self.seen: list[Any] = []

    def on_blackout_onset(self, onset: Any) -> None:
        """Record one onset."""
        self.seen.append(onset)


class _Clock:
    """A settable UTC clock. `now` is DRIVEN; nothing reads the wall."""

    def __init__(self, at: dt.datetime) -> None:
        self.at = at

    def __call__(self) -> dt.datetime:
        return self.at


class _PendingBook:
    """`PendingEntriesPort` over a mutable list."""

    def __init__(self, entries: list[Any]) -> None:
        self.entries = entries

    def pending_entries(self) -> tuple[Any, ...]:
        """Every pending ENTRY order."""
        return tuple(self.entries)


class _Inert:
    """A collaborator the ONSET SWEEP must never reach. Raises on every verb."""

    def __init__(self, role: str) -> None:
        self._role = role

    def __getattr__(self, verb: str) -> Any:
        raise AssertionError(
            f"the onset sweep reached {self._role}.{verb} — §3:173 cancels pending "
            "ENTRY orders and releases their reservations, and nothing else; a "
            "sweep that publishes a picture or fans out to Scoring is doing the "
            "exit path's job"
        )


def _executor(broker: Any, ledger: Any, plane1: Any, *, aborting: bool = False) -> Any:
    """The flatten executor wired for an ONSET SWEEP and nothing else.

    `picture` / `strategy` / `scoring` are inert doubles rather than the real
    collaborators, and that is a statement about the subject: §3:173's sweep calls
    `cancel_order` and the reservation ledger and touches nothing else — a sweep
    that published a picture or fanned out to Scoring would be doing the exit
    path's job. If the sweep ever reaches one of them, `_Inert` raises and the
    control fails loudly rather than passing over a widened subject.

    Every parameter is `Any` because the arguments are deliberate PORT DOUBLES: the
    tree's `StubBrokerOrder` satisfies `BrokerFlattenPort` structurally at runtime
    (that is the whole point of a declared-narrow port) and mypy's list invariance
    rejects `list[Position]` against `list[_BrokerPosition]` anyway. Widening here
    rather than sprinkling `type: ignore` keeps the suppression in ONE place with
    ONE reason.
    """
    builder: Any = _AbortingSweep if aborting else fl.ProtectiveFlatten
    return builder(
        broker=broker,
        ledger=ledger,
        picture=_Inert("picture"),
        strategy=_Inert("strategy"),
        plane1=plane1,
        scoring=_Inert("scoring"),
    )


def _knobs() -> Any:
    import json  # pylint: disable=import-outside-toplevel

    config = REPO / "risks" / "limiter.config.json"
    values = json.loads(config.read_text(encoding="utf-8")) if config.is_file() else {}
    return bl.BlackoutKnobs.from_config(values)


async def _working_entry(coid: str) -> tuple[Any, Any, _Plane1, ReservationLedger]:
    """A gate-APPROVED entry, its reservation taken, WORKING at a real broker."""
    plane1 = _Plane1()
    ledger = ReservationLedger(plane1)
    outcome = g.GatePass(_Clear(), list(_manifest()), ledger).evaluate(
        _proposal(coid=coid), _picture(), 0.0
    )
    assert outcome.decision is Decision.APPROVE, outcome
    assert outcome.reservation_id is not None
    sink = RecordingSink()
    broker = StubBrokerOrder(sink)
    await broker.connect()
    broker.place_order(
        NeutralOrder(coid, SYMBOL, BrokerSide.BUY, 2, OrderType.MARKET, TimeInForce.DAY)
    )
    assert coid in broker._working  # pylint: disable=protected-access
    return broker, sink, plane1, ledger


def _filled_inside_the_window(broker: Any, coid: str) -> bool:
    """Did the order still fill? `simulate_fill` raises once it is off the book."""
    try:
        broker.simulate_fill(coid, 2, 5_000.0)
    except KeyError:
        return False
    return True


def _onset_rig(coid: str, *, wired: bool):
    """The real evaluator over a real EOD edge, with the sweep wired or not."""
    broker, sink, plane1, ledger = asyncio.run(_working_entry(coid))
    knobs = _knobs()
    source = bl.SessionWindowSource(knobs)
    day = dt.datetime(2026, 8, 20, 12, 0, tzinfo=UTC)  # a Thursday
    window_set = source.window_set(SYMBOL, day)
    window = min(window_set.windows, key=lambda w: w.start)
    clock = _Clock(window.start - dt.timedelta(seconds=1))
    onsets = _Onsets()
    extra: dict[str, Any] = {}
    if wired:
        extra = {
            "sweep": _executor(broker, ledger, plane1),
            "pending": _PendingBook(
                [fl.PendingEntry(client_order_id=coid, strategy_id="s1", symbol=SYMBOL)]
            ),
        }
    evaluator = bl.BlackoutEvaluator(
        windows=_WindowCache(window_set),
        baselines=_BaselineCache(),
        picture=_PictureRead(),
        clock=clock,
        knobs=knobs,
        onset=onsets,
        ledger=ledger,
        **extra,
    )
    return evaluator, clock, window, onsets, broker, sink, ledger


def test_a_BLACKOUT_ONSET_CANCELS_the_working_ENTRY_at_the_venue() -> None:
    """FA-2. §15:995 C4 and §3:172-174, driven to the venue and not to a record.

    BOTH HALVES, and they must DISAGREE. Unwired (the pre-repair behaviour) the
    reservation is released and the order still FILLS inside the window. Wired, the
    order is off the venue's book and CANNOT fill.
    """
    # -- UNPROTECTED HALF ------------------------------------------------
    ev, clock, window, onsets, broker, _sink, ledger = _onset_rig(
        "c-unwired", wired=False
    )
    assert ev.read(SYMBOL)[0] is False, "the drive must start OUTSIDE the window"
    clock.at = window.start
    blocked, reason = ev.read(SYMBOL)
    assert blocked and window.kind.value in reason, reason
    assert len(onsets.seen) == 1, onsets.seen
    assert onsets.seen[0].released, "the reservation was not released"
    assert ledger.total_reserved() == 0.0, ledger.total_reserved()
    assert _filled_inside_the_window(broker, "c-unwired") is True, (
        "the unprotected half did NOT reproduce the violation, so the protected "
        "half below would prove nothing (ARC 035)"
    )

    # -- PROTECTED HALF --------------------------------------------------
    ev, clock, window, onsets, broker, sink, ledger = _onset_rig("c-wired", wired=True)
    assert ev.read(SYMBOL)[0] is False
    clock.at = window.start
    assert ev.read(SYMBOL)[0] is True
    assert len(onsets.seen) == 1, onsets.seen
    assert onsets.seen[0].via is TerminalPath.BLACKOUT_ONSET, onsets.seen[0]
    assert onsets.seen[0].released, "the onset released no reservation"
    assert ledger.total_reserved() == 0.0, ledger.total_reserved()
    assert [coid for coid, _done in sink.cancels] == ["c-wired"], sink.cancels
    assert _filled_inside_the_window(broker, "c-wired") is False, (
        "the entry FILLED inside the window after the wired onset — §3:174: no "
        "order may fill inside a window it was not approved for"
    )


def test_the_BLACKOUT_ONSET_SWEEP_is_BOTH_ports_or_NEITHER() -> None:
    """FA-2. Half-wiring would report a successful cancellation of zero orders."""
    knobs = _knobs()
    with pytest.raises(bl.BlackoutKnobError) as exc:
        bl.BlackoutEvaluator(
            windows=_WindowCache(None),
            baselines=_BaselineCache(),
            picture=_PictureRead(),
            clock=_Clock(dt.datetime(2026, 8, 20, 12, 0, tzinfo=UTC)),
            knobs=knobs,
            pending=_PendingBook([]),
        )
    assert "BOTH the executor and the pending-" in str(exc.value), str(exc.value)


# ===========================================================================
# FA-3 — a refused cancel does not ABORT the onset sweep
# ===========================================================================


class _AbortingSweep(fl.ProtectiveFlatten):
    """FALSIFIER: `cancel_entries_on_onset` as it was BEFORE the repair.

    The pre-repair loop, verbatim in behaviour: an unguarded `cancel_order` per
    entry, so the first refusal propagates and every later entry is never
    attempted. Kept here rather than staged into a file copy because the defect is
    one statement's exception handling, and a subclass makes the two halves
    comparable inside one process.
    """

    def cancel_entries_on_onset(self, cause: Any, pending: Any) -> Any:
        cancelled: list[str] = []
        for entry in pending:
            self._broker.cancel_order(entry.client_order_id)  # pylint: disable=protected-access
            self._ledger.resolve(  # pylint: disable=protected-access
                entry.client_order_id, cause, 0.0, reason=cause.value
            )
            cancelled.append(entry.client_order_id)
        return fl.OnsetCancellation(
            cause=cause, cancelled=tuple(cancelled), released=(), refusals=()
        )


def _three_entries(refuse: str, *, aborting: bool):
    """Three working entries, three reservations, and a broker refusing one cancel."""
    plane1 = _Plane1()
    ledger = ReservationLedger(plane1)
    sink = RecordingSink()
    broker = StubBrokerOrder(sink)
    asyncio.run(broker.connect())
    coids = ["c-1", "c-2", "c-3"]
    for coid in coids:
        ledger.take(_proposal(coid=coid), 0.0)
        broker.place_order(
            NeutralOrder(
                coid, SYMBOL, BrokerSide.BUY, 2, OrderType.MARKET, TimeInForce.DAY
            )
        )
    real = broker.cancel_order

    def refusing(client_order_id: str) -> None:
        if client_order_id == refuse:
            raise BrokerNotConnected(
                f"cancel_order called with no session ({client_order_id})"
            )
        real(client_order_id)

    broker.cancel_order = refusing  # type: ignore[method-assign]
    executor = _executor(broker, ledger, plane1, aborting=aborting)
    entries = [
        fl.PendingEntry(client_order_id=coid, strategy_id="s1", symbol=SYMBOL)
        for coid in coids
    ]
    flag = hl.HaltFlag(
        plane1=plane1,
        plane2=_Plane2(),
        floors=FLOORS,
        onset=executor,
        pending=_PendingBook(entries),
    )
    return flag, broker, ledger, plane1, coids


class _UnbookingHaltFlag(hl.HaltFlag):
    """FALSIFIER: `_sweep_pending_entries` as it was BEFORE the repair.

    The pre-repair call was UNGUARDED and `set()` runs it before `self._book` and
    before `record_booked`, so an exception from the sweep took the §12.10:753
    `halt_set` row and the marker's `booked` record down with it — a HALT that is
    declared, gates money, and leaves no record that it happened.
    """

    def _sweep_pending_entries(self) -> str:
        onset = self._onset  # pylint: disable=protected-access
        pending = self._pending  # pylint: disable=protected-access
        if onset is None or pending is None:
            return hl.SWEEP_NOT_WIRED
        onset.cancel_entries_on_onset(
            TerminalPath.HALT_ONSET, tuple(pending.pending_entries())
        )
        return hl.SWEEP_RAN


def test_a_REFUSED_CANCEL_does_not_ABORT_the_onset_sweep() -> None:
    """FA-3(i). §3:173 cancels ALL pending entries; one refusal must not stop the rest.

    BOTH HALVES, taken on the EXECUTOR directly so the subject is the loop and not
    the HALT machine wrapped around it. The unprotected half is the pre-repair
    unguarded loop and must leave the entry AFTER the refusal working; the
    protected half must leave only the genuinely-refused one.
    """
    # -- UNPROTECTED HALF: the pre-repair loop ---------------------------
    flag, broker, ledger, plane1, _coids = _three_entries("c-2", aborting=True)
    del flag
    executor: Any = _executor(broker, ledger, plane1, aborting=True)
    entries = [
        fl.PendingEntry(client_order_id=coid, strategy_id="s1", symbol=SYMBOL)
        for coid in ("c-1", "c-2", "c-3")
    ]
    with pytest.raises(BrokerNotConnected) as exc:
        executor.cancel_entries_on_onset(TerminalPath.HALT_ONSET, entries)
    assert "c-2" in str(exc.value), str(exc.value)
    survivors = sorted(broker._working)  # pylint: disable=protected-access
    assert survivors == ["c-2", "c-3"], (
        f"the unprotected half did not reproduce the abort: survivors={survivors}. "
        "c-3 must survive — it was never ATTEMPTED"
    )
    assert _filled_inside_the_window(broker, "c-3") is True, (
        "c-3 could not fill, so the consequence this finding is about did not appear"
    )
    assert ledger.total_reserved() == 4_000.0, ledger.total_reserved()

    # -- PROTECTED HALF: the shipped loop --------------------------------
    flag, broker, ledger, plane1, _coids = _three_entries("c-2", aborting=False)
    del flag
    executor = _executor(broker, ledger, plane1)
    outcome = executor.cancel_entries_on_onset(TerminalPath.HALT_ONSET, entries)
    assert outcome.complete is False, outcome
    assert [coid for coid, _why in outcome.failures] == ["c-2"], outcome.failures
    assert "BrokerNotConnected" in outcome.failures[0][1], outcome.failures
    assert sorted(outcome.cancelled) == ["c-1", "c-3"], outcome.cancelled
    survivors = sorted(broker._working)  # pylint: disable=protected-access
    assert survivors == ["c-2"], (
        f"the sweep did not complete past the refusal: survivors={survivors}"
    )
    cancels = plane1.of(EventKind.CANCEL)
    assert len(cancels) == 3, f"one row per pending entry, got {len(cancels)}"
    refused = [row for row in cancels if "REFUSED by the broker" in row.reason]
    assert len(refused) == 1, [row.reason for row in cancels]
    assert "STILL WORKING at the venue" in refused[0].reason, refused[0].reason
    # The refused entry KEEPS its reservation — the order is live, so the margin
    # must stay committed. That is the safe direction, not a leak.
    assert ledger.total_reserved() == 2_000.0, ledger.total_reserved()


def test_a_PARTIAL_sweep_still_books_the_HALT_SET_row() -> None:
    """FA-3(ii). §12.10:753 owes a `halt_set` row on EVERY transition.

    BOTH HALVES. Unprotected, the pre-repair unguarded sweep call lets the
    exception escape `set()` and NO row is booked; protected, the row is booked and
    the `onset_sweep` field says `partial` rather than claiming a clean sweep.
    """
    # -- UNPROTECTED HALF ------------------------------------------------
    plane1 = _Plane1()
    ledger = ReservationLedger(plane1)
    sink = RecordingSink()
    broker = StubBrokerOrder(sink)
    asyncio.run(broker.connect())
    ledger.take(_proposal(coid="c-1"), 0.0)
    broker.place_order(
        NeutralOrder(
            "c-1", SYMBOL, BrokerSide.BUY, 2, OrderType.MARKET, TimeInForce.DAY
        )
    )

    def always_refuses(client_order_id: str) -> None:
        raise BrokerNotConnected(
            f"cancel_order called with no session ({client_order_id})"
        )

    broker.cancel_order = always_refuses  # type: ignore[method-assign]
    entries = [_PendingBook([fl.PendingEntry("c-1", "s1", SYMBOL)])]
    unguarded = _UnbookingHaltFlag(
        plane1=plane1,
        plane2=_Plane2(),
        floors=FLOORS,
        onset=_executor(broker, ledger, plane1, aborting=True),
        pending=entries[0],
    )
    with pytest.raises(BrokerNotConnected):
        unguarded.set(hl.HaltCause.STALE_DATA, "feed stopped")
    assert unguarded.is_set()[0] is True, "the flag must be up — money is gated"
    assert not plane1.of(EventKind.HALT_SET), (
        "the unprotected half booked a halt_set row, so the §12.10:753 half of this "
        "finding did not reproduce and the protected half proves less"
    )

    # -- PROTECTED HALF --------------------------------------------------
    flag, broker, ledger, plane1, _coids = _three_entries("c-2", aborting=False)
    transition = flag.set(hl.HaltCause.STALE_DATA, "feed stopped")
    assert transition.booked is True, transition
    assert transition.swept is False, "a partial sweep must not claim a clean one"
    assert transition.sweep == hl.SWEEP_PARTIAL, transition
    rows = plane1.of(EventKind.HALT_SET)
    assert len(rows) == 1, f"§12.10:753 owes exactly one halt_set row, got {len(rows)}"
    assert rows[0].fields["onset_sweep"] == hl.SWEEP_PARTIAL, rows[0].fields
    survivors = sorted(broker._working)  # pylint: disable=protected-access
    assert survivors == ["c-2"], survivors


def test_a_CLEAN_sweep_still_reports_RAN_and_cancels_EVERY_entry() -> None:
    """FA-3's control: the repair must not turn a good sweep into a partial one."""
    flag, broker, ledger, plane1, _coids = _three_entries("none", aborting=False)
    transition = flag.set(hl.HaltCause.CLOCK_SKEW, "skew")
    assert transition.swept is True, transition
    assert transition.sweep == hl.SWEEP_RAN, transition
    assert not broker._working, broker._working  # pylint: disable=protected-access
    assert ledger.total_reserved() == 0.0, ledger.total_reserved()
    assert plane1.of(EventKind.HALT_SET)[0].fields["onset_sweep"] == hl.SWEEP_RAN
    assert not [row for row in plane1.of(EventKind.CANCEL) if "REFUSED" in row.reason]


def test_an_UNWIRED_SWEEP_is_still_DISTINGUISHABLE_from_a_clean_one() -> None:
    """FA-3. Three states, not two: `ran`, `partial`, `not_wired`."""
    plane1 = _Plane1()
    flag = hl.HaltFlag(plane1=plane1, plane2=_Plane2(), floors=FLOORS)
    assert flag.sweep_wired is False
    transition = flag.set(hl.HaltCause.STALE_DATA, "silent")
    assert transition.sweep == hl.SWEEP_NOT_WIRED, transition
    assert plane1.of(EventKind.HALT_SET)[0].fields["onset_sweep"] == hl.SWEEP_NOT_WIRED
    assert {hl.SWEEP_RAN, hl.SWEEP_PARTIAL, hl.SWEEP_NOT_WIRED, hl.SWEEP_SKIPPED} == {
        "ran",
        "partial",
        "not_wired",
        "skipped",
    }


def test_the_ONSET_CANCEL_and_a_FILL_are_SAFE_in_BOTH_ORDERINGS() -> None:
    """FA-6 / I11. The reservation reaches EXACTLY ONE terminal release either way.

    BOTH ORDERINGS, because a race is only measured by driving both: an assertion
    that holds in one ordering says nothing about the other, and `StubBrokerOrder`
    is single-threaded so the orderings are what this boundary can produce (a true
    interleaving needs the threaded IBKR adapter — `test_broker_tier3.py` owns it).

    **THE RESIDUAL THIS CONTROL DELIBERATELY DOES NOT CLAIM — FA-6, CHECK-DEBT.**
    In ordering 2 the entry has ALREADY FILLED when the sweep reaches it, and the
    sweep releases its reservation under the ONSET cause. §3:150-152 is explicit
    that a FILL release *"converts to open-margin"*, which is a different fact, so
    `committed` momentarily under-counts by the margin of a REAL position and §9's
    row names the wrong terminal path. That is asserted here as the CURRENT
    behaviour rather than as correct behaviour, so the day it is repaired this
    control fails and points at the finding. What IS claimed as correct is the
    §14 arithmetic: exactly one terminal release, in both orderings.
    """
    entries = [fl.PendingEntry("c-race", "s1", SYMBOL)]

    # -- ORDERING 1: the onset cancel lands FIRST -------------------------
    plane1 = _Plane1()
    ledger = ReservationLedger(plane1)
    broker = StubBrokerOrder(RecordingSink())
    asyncio.run(broker.connect())
    ledger.take(_proposal(coid="c-race"), 0.0)
    broker.place_order(
        NeutralOrder(
            "c-race", SYMBOL, BrokerSide.BUY, 2, OrderType.MARKET, TimeInForce.DAY
        )
    )
    outcome = _executor(broker, ledger, plane1).cancel_entries_on_onset(
        TerminalPath.HALT_ONSET, entries
    )
    assert outcome.complete is True, outcome
    assert ledger.total_reserved() == 0.0, ledger.total_reserved()
    assert _filled_inside_the_window(broker, "c-race") is False, (
        "a fill landed AFTER the cancel — the venue book still had the order"
    )
    assert broker.query_order_status("c-race").state == "cancelled"
    assert len(ledger.released()) == 1, ledger.released()

    # -- ORDERING 2: the FILL lands first ---------------------------------
    plane1 = _Plane1()
    ledger = ReservationLedger(plane1)
    broker = StubBrokerOrder(RecordingSink())
    asyncio.run(broker.connect())
    ledger.take(_proposal(coid="c-race"), 0.0)
    broker.place_order(
        NeutralOrder(
            "c-race", SYMBOL, BrokerSide.BUY, 2, OrderType.MARKET, TimeInForce.DAY
        )
    )
    assert _filled_inside_the_window(broker, "c-race") is True, "the fill must land"
    held = asyncio.run(broker.query_positions())
    assert [(pos.symbol, pos.net_qty) for pos in held] == [(SYMBOL, 2)], held
    outcome = _executor(broker, ledger, plane1).cancel_entries_on_onset(
        TerminalPath.HALT_ONSET, entries
    )
    assert outcome.complete is True, outcome
    released = ledger.released()
    assert len(released) == 1, f"§14: exactly one terminal release, got {released}"
    # THE RESIDUAL, asserted as current behaviour and named as wrong (FA-6): the
    # cause is the ONSET, not FILL, and Σ reservations went to zero while the
    # position is real.
    assert released[0].released_via is TerminalPath.HALT_ONSET, released[0]
    assert ledger.total_reserved() == 0.0, ledger.total_reserved()
    still_held = asyncio.run(broker.query_positions())
    assert [(pos.symbol, pos.net_qty) for pos in still_held] == [(SYMBOL, 2)], (
        "the cancel must be a NO-OP on a terminal-filled order; a cancel that "
        "closed a position would be the §3:173 'exits untouched' violation"
    )


def test_EVERY_HaltCause_SWEEPS_on_the_onset_edge() -> None:
    """FA-3 / I11's cause taxonomy: no §12.5:631 cause enters HALT without a sweep."""
    for cause in hl.HaltCause:
        flag, broker, _ledger, _plane1, _coids = _three_entries("none", aborting=False)
        transition = flag.set(cause, "drive")
        assert transition.sweep == hl.SWEEP_RAN, (cause, transition)
        assert not broker._working, (  # pylint: disable=protected-access
            f"{cause.value} entered HALT with entries still working"
        )


# ===========================================================================
# FA-5 — the reach set to a mutating order verb
# ===========================================================================

#: Read-only order-port verbs. Everything else on the roster MOVES MONEY, so a
#: verb added to `ORDER_PORT_VERBS` joins the ban set fail-closed rather than
#: needing an edit here.
READ_ONLY_VERBS = frozenset(
    {
        "connect",
        "disconnect",
        "query_positions",
        "query_balance",
        "query_order_status",
        "get_margin",
    }
)

#: The directories a mutating order verb may be CALLED from. `scripts/broker` is
#: the adapter (it IS the order path); `scripts/nixrisk` is the Limiter, which
#: §14:966 makes the only thing allowed to reach broker-order. `scripts/tests` is
#: excluded and the exclusion is COUNTED below so it can never become invisible.
#: A LITERAL on purpose: derived from the tree it would agree with any tree.
ALLOWED_REACH_DIRS = ("scripts/broker", "scripts/nixrisk")

#: The measured non-test reach set at the time of writing, as a LITERAL. It is not
#: derived from the scan, because a scan compared against itself passes on any
#: tree (D3.192's reasoning). It grows only by a deliberate edit.
EXPECTED_REACH = {
    "scripts/broker/broker_order_ibkr.py",
    "scripts/broker/seam_simulate.py",
    "scripts/nixrisk/coldstart.py",
    "scripts/nixrisk/fills.py",
    "scripts/nixrisk/flatten.py",
    "scripts/nixrisk/survival.py",
}


def _mutating_verbs() -> frozenset[str]:
    return frozenset(ORDER_PORT_VERBS) - READ_ONLY_VERBS


def _classify(
    rel: str, node: ast.AST, verbs: frozenset[str], called: set[int]
) -> tuple[tuple[str, int, str] | None, str | None]:
    """`(direct_call, indirect_reach)` for ONE AST node. At most one is not None.

    Three shapes, and a direct-call scan alone would miss two of them:

    * `x.place_order(...)` — the DIRECT call;
    * `getattr(x, "place_order")` — the verb named by a STRING, invisible to any
      attribute scan;
    * `send = x.place_order` — the verb loaded as a VALUE and called elsewhere,
      which is how a bound method crosses a module boundary.

    One function per node rather than three predicates inside the walk loop: the
    walk then has no nesting at all, and each shape is read against the node kind
    it names.
    """
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Attribute) and node.func.attr in verbs:
            return (rel, node.lineno, node.func.attr), None
        if (
            isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and node.args[1].value in verbs
        ):
            return None, f"{rel}:{node.lineno} getattr reach"
        return None, None
    if (
        isinstance(node, ast.Attribute)
        and node.attr in verbs
        and id(node) not in called
    ):
        return None, f"{rel}:{node.lineno} bound-method load .{node.attr}"
    return None, None


def _reach(sources: dict[str, str]) -> tuple[list[tuple[str, int, str]], list[str]]:
    """Every CALL of a mutating order verb, plus every INDIRECT reach.

    The classification is `_classify`'s; this is the walk and nothing else, so the
    scope of the scan (which files, which nodes) is readable separately from what
    counts as a reach.
    """
    verbs = _mutating_verbs()
    calls: list[tuple[str, int, str]] = []
    indirect: list[str] = []
    for rel, src in sources.items():
        tree = ast.parse(src, filename=rel)
        called = {
            id(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)
        }
        for node in ast.walk(tree):
            call, reach = _classify(rel, node, verbs, called)
            if call is not None:
                calls.append(call)
            if reach is not None:
                indirect.append(reach)
    return calls, indirect


def _production_sources() -> dict[str, str]:
    sources: dict[str, str] = {}
    skipped: list[str] = []
    for dirpath, dirnames, filenames in os.walk(REPO / "scripts"):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for filename in sorted(filenames):
            if not filename.endswith(".py"):
                continue
            path = Path(dirpath) / filename
            rel = str(path.relative_to(REPO))
            if rel.startswith("scripts/tests/"):
                skipped.append(rel)
                continue
            try:
                sources[rel] = path.read_text(encoding="utf-8")
                ast.parse(sources[rel], filename=rel)
            except (SyntaxError, UnicodeDecodeError) as exc:  # pragma: no cover
                pytest.fail(
                    f"{rel} would not parse ({exc}) — a file the scan cannot open is a "
                    "file the reach set silently does not cover (§7.12)"
                )
    assert len(sources) >= 90, (
        f"only {len(sources)} production module(s) scanned; the reach set over a tree "
        "this small is not a measurement of this tree"
    )
    assert len(skipped) >= 40, f"only {len(skipped)} test module(s) excluded: {skipped}"
    return sources


def test_the_ORDER_PORT_REACH_SET_is_exactly_the_LIMITER_and_the_ADAPTER() -> None:
    """FA-5 / I1. §14:966: nothing reaches broker-order without passing the Limiter.

    BOTH HALVES. The unprotected half hands the same scanner a synthetic module
    outside both allowed directories and REQUIRES it to be reported; the protected
    half scans the real tree and requires the reach set to be exactly the literal
    roster above.
    """
    verbs = _mutating_verbs()
    assert verbs == {"place_order", "cancel_order", "flatten"}, verbs

    # -- UNPROTECTED HALF: a reach the scanner must SEE -------------------
    rogue = {
        "scripts/rogue_dispatcher.py": (
            "def send(broker, order):\n"
            "    broker.place_order(order)\n"
            "    handler = getattr(broker, 'flatten')\n"
            "    return handler\n"
        )
    }
    calls, indirect = _reach(rogue)
    assert [rel for rel, _ln, _verb in calls] == ["scripts/rogue_dispatcher.py"], calls
    assert any("getattr reach" in item for item in indirect), indirect

    # -- PROTECTED HALF: the real tree ------------------------------------
    sources = _production_sources()
    calls, indirect = _reach(sources)
    reached = {rel for rel, _ln, _verb in calls}
    assert reached == EXPECTED_REACH, (
        f"the reach set moved.\n  ADDED: {sorted(reached - EXPECTED_REACH)}\n"
        f"  GONE : {sorted(EXPECTED_REACH - reached)}\n"
        "§14:966 makes the Limiter the only thing that may reach broker-order; a new "
        "call site must be shown to sit behind a GatePass before this roster grows"
    )
    outside = sorted(rel for rel in reached if not rel.startswith(ALLOWED_REACH_DIRS))
    assert not outside, (
        f"a mutating order verb is called from outside the Limiter and the adapter: "
        f"{outside}"
    )
    stray = [
        item
        for item in indirect
        if not item.startswith("scripts/broker/seam_simulate.py")
    ]
    assert not stray, (
        f"an INDIRECT reach to the order port exists outside the adapter's own "
        f"conformance driver: {stray}"
    )
    # The half of I1 that has no subject, asserted so it cannot quietly acquire one
    # without this control noticing (FA-5, CHECK-DEBT).
    entry_sends = [
        (rel, ln)
        for rel, ln, verb in calls
        if verb == "place_order" and "nixrisk" in rel
    ]
    assert not entry_sends, (
        f"the Limiter now has an ENTRY dispatch path ({entry_sends}) — I1's entry half "
        "acquired a subject, and it must be shown to run only behind a GatePass"
    )
