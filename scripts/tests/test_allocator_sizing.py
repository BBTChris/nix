"""ARC 031 / B — behaviour of the Allocator's sizing pathway.

Four properties, each MEASURED rather than asserted about, and each with the
falsifier that shows the measurement could have failed:

* **B1 — single-pass ordering (§16 U1).** Execution order, not source order.
  Every arithmetic step in `nixalloc.sizing` is a module-level function, so the
  tests below replace them with recorders, share one call log with recording
  mirror and tradability ports, and read what ACTUALLY RAN. The falsifier is
  `_SizesFirst`, a deliberately wrong allocator built here that calls the
  arithmetic before the tradability cache: the same instrument catches it.
* **B2 — headroom = DEPLOYABLE_PCT × balance − committed (§16 U2).** Measured
  against a picture whose published `committed` deliberately DISAGREES with the
  sum of its own position rows, plus a position table that counts its own
  traversals and must be traversed zero times.
* **B3 — §15 C3 / §7 guards**, both branches of §16 U4's fulls-vs-micros rule
  driven, and the slippage pad shown to change the answer.
* **B4 — the Allocator and the real `nixrisk.gate.GatePass` read identical
  bytes for one version stamp**, observed through a recording picture handed to
  both, with the one place the gate does NOT read the picture named explicitly.

Every §-citation resolves against `docs/nics_risk_subsystem_spec_v1.3.md`.
"""
# pylint: disable=invalid-name,redefined-outer-name,protected-access
# pylint: disable=too-few-public-methods,duplicate-code
# pylint: disable=too-many-arguments,too-many-positional-arguments
# `_picture` and `_allocator` take one keyword per DIMENSION the tests vary
# (balance, committed, rows, margins, version, and the two aggregates). Folding
# them into a struct would hide which dimension a given test is moving, which is
# the whole readability of a table-driven suite.
# Test names SHOUT the property; the sys.path bootstrap is identical in every
# test module by requirement.

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from nixalloc import sizing  # pylint: disable=wrong-import-position
from nixalloc.seam import (  # pylint: disable=wrong-import-position
    BindingConstraint,
    ContentionPolicy,
    FinancialPicture,
    MirrorSnapshot,
    MirrorState,
    PositionRow,
    PositionState,
    ProposalOutcome,
    Side,
    StopMode,
)
from nixalloc.sizing import (  # pylint: disable=wrong-import-position
    NO_SNAPSHOT,
    InstrumentSpec,
    SizingAllocator,
    SizingConfigError,
    SizingKnobs,
    load_sizing_knobs,
)

# --------------------------------------------------------------------------
# The population — every double records, so ORDER is readable
# --------------------------------------------------------------------------

#: Injected rather than read from `risks/`: `tick_value` is an instrument
#: constant delivered on the registration ACK (`nix_strategy_contract_v1.1.md`
#: §7.2). ES = $12.50/tick is the CME figure that contract itself prints.
#:
#: The risk spec's tunables list declares no TICK_VALUE knob, so `risks/` is
#: not where this number could have come from.
ES = InstrumentSpec(symbol="ES", micro_symbol="MES", tick_value=12.5, micro_ratio=10)

TRADABLE = "tradability.tradable"
SNAPSHOT = "mirror.snapshot"
VERSION = "mirror.version"

#: The names the recorders append. Every one is a module-level function in
#: `nixalloc.sizing`, which is what makes the substitution possible at all.
ARITHMETIC: tuple[str, ...] = (
    "headroom_usd",
    "dollar_risk_per_contract",
    "risk_contracts",
    "margin_contracts",
    "select_instrument",
)


class _RecordingTradability:
    """The §16 U1 fast-drop cache, recording the moment it is read."""

    def __init__(
        self, log: list[str], tradable: bool = True, why: str = "open"
    ) -> None:
        self._log = log
        self._tradable = tradable
        self._why = why

    def tradable(self, symbol: str) -> tuple[bool, str]:
        """`(tradable, reason)` — and a mark at the position it was consulted."""
        del symbol
        self._log.append(TRADABLE)
        return self._tradable, self._why


class _RecordingMirror:
    """A `MirrorPort` that records every read. Never mutates, never publishes."""

    def __init__(
        self,
        log: list[str],
        picture: Any,
        state: MirrorState = MirrorState.FRESH,
        reason: str = "snapshot applied",
    ) -> None:
        self._log = log
        self._picture = picture
        self._state = state
        self._reason = reason

    def snapshot(self) -> MirrorSnapshot:
        """One local read, recorded."""
        self._log.append(SNAPSHOT)
        return MirrorSnapshot(
            state=self._state,
            picture=self._picture if self._state is MirrorState.FRESH else None,
            reason=self._reason,
        )

    def version(self) -> int:
        """The stamp, recorded. Negative when there is no picture."""
        self._log.append(VERSION)
        return NO_SNAPSHOT if self._picture is None else int(self._picture.version)


class _CountingPositions(tuple):  # type: ignore[type-arg]
    """A position table that counts every row anything pulls out of it.

    §11.3 keeps `committed` as a running aggregate that arrives PRECOMPUTED on
    the snapshot, and §16 U2 makes reading it — rather than re-deriving it —
    the correction that killed v1.1's size-down churn. A sizer that re-summed
    the rows would satisfy every arithmetic assertion in this file and produce
    a non-zero count here.
    """

    traversals = 0

    def __iter__(self) -> Any:
        for row in tuple.__iter__(self):
            type(self).traversals += 1
            yield row

    def __getitem__(self, index: Any) -> Any:
        type(self).traversals += 1
        return tuple.__getitem__(self, index)


def _rows(*margins: float) -> tuple[PositionRow, ...]:
    return tuple(
        PositionRow(
            trade_id=f"t{i}",
            symbol="ES",
            strategy_id="s1",
            size=1,
            margin=margin,
            state=PositionState.OPEN,
        )
        for i, margin in enumerate(margins)
    )


def _picture(
    *,
    balance: float = 100_000.0,
    committed: float = 10_000.0,
    positions: tuple[PositionRow, ...] = (),
    margins: dict[str, float] | None = None,
    version: int = 41,
    sum_open: float | None = None,
    sum_res: float = 0.0,
) -> FinancialPicture:
    """One published snapshot. `committed` is a FIELD, never a derivation."""
    return FinancialPicture(
        version=version,
        published_ts=1_700_000_000.0,
        balance=balance,
        positions=positions,
        margin_per_contract=MappingProxyType(
            dict(margins if margins is not None else {"ES": 500.0, "MES": 50.0})
        ),
        sum_open_margin=committed if sum_open is None else sum_open,
        sum_reservations=sum_res,
        committed=committed,
        deployable=balance * 0.70 - committed,
    )


def _knobs(**overrides: Any) -> SizingKnobs:
    """A knob set with the §12A shape. Overridable so a term can be made to bind."""
    base: dict[str, Any] = {
        "per_trade_risk_usd": 100.0,
        "deployable_pct": 0.70,
        "symbol_cap": {"ES": 5},
        "slippage_pad_ticks": {"ES": 2},
        "micro_full_threshold": 2,
        "quant_tolerance": 0.25,
    }
    base.update(overrides)
    return SizingKnobs(**base)


def _allocator(
    log: list[str],
    picture: Any,
    *,
    knobs: SizingKnobs | None = None,
    tradable: bool = True,
    state: MirrorState = MirrorState.FRESH,
    instruments: dict[str, InstrumentSpec] | None = None,
) -> SizingAllocator:
    return SizingAllocator(
        mirror=_RecordingMirror(log, picture, state),
        tradability=_RecordingTradability(log, tradable),
        instruments={"ES": ES} if instruments is None else instruments,
        knobs=knobs or _knobs(),
        bucket_cap=None,
    )


def _go(allocator: SizingAllocator, stop_ticks: int = 4) -> Any:
    return allocator.propose("s1", "ES", Side.LONG, stop_ticks, StopMode.FIXED, 1.5)


@pytest.fixture
def watched(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Replace every arithmetic function with a recorder over one shared log.

    This is the whole B1 instrument. The functions are module globals and
    `SizingAllocator` calls them through the module namespace, so what is
    measured afterwards is the sequence of calls that HAPPENED — not the order
    they are written in, which is a different fact and not the one §16 U1 is
    about.
    """
    log: list[str] = []
    for name in ARITHMETIC:
        real = getattr(sizing, name)

        def recorder(
            *args: Any, _real: Any = real, _name: str = name, **kw: Any
        ) -> Any:
            log.append(_name)
            return _real(*args, **kw)

        monkeypatch.setattr(sizing, name, recorder)
    return log


# ==========================================================================
# B1 — SINGLE-PASS ORDERING (§16 U1). EXECUTION order, not source order.
# ==========================================================================


def test_B1_a_DEAD_SIGNAL_IS_DROPPED_BEFORE_THE_MIRROR_OR_ANY_ARITHMETIC_RUNS(
    watched: list[str],
) -> None:
    """§16 U1: never size a dead signal. Proven by what the log DOES NOT hold."""
    proposal = _go(_allocator(watched, _picture(), tradable=False))

    assert watched == [TRADABLE], (
        "the tradability cache must be the FIRST and — on a dead signal — the "
        f"ONLY thing consulted; the pass actually ran {watched}"
    )
    assert proposal.outcome is ProposalOutcome.NOT_TRADABLE, proposal
    assert proposal.contracts == 0 and proposal.order is None, proposal
    assert proposal.rationale.snapshot_version == NO_SNAPSHOT, (
        "a drop that never read the mirror must not claim a snapshot version"
    )


def test_B1_the_INSTRUMENT_CATCHES_AN_ALLOCATOR_THAT_SIZES_FIRST(
    watched: list[str],
) -> None:
    """THE FALSIFIER. Without this, the test above could be measuring nothing.

    `_SizesFirst` is the defect B1 exists to reject, built here and driven
    through the SAME instrument. If the log could not tell the two apart, the
    assertion above would be satisfied by any implementation at all.
    """

    class _SizesFirst:
        """Sizes, then asks whether the symbol was even tradable. Wrong on purpose."""

        def __init__(self, mirror: Any, tradability: Any) -> None:
            self._mirror = mirror
            self._tradability = tradability

        def propose(self) -> None:
            """The §16 U1 violation, executed."""
            snapshot = self._mirror.snapshot()
            sizing.headroom_usd(snapshot.picture, 0.70)
            self._tradability.tradable("ES")

    _SizesFirst(
        _RecordingMirror(watched, _picture()),
        _RecordingTradability(watched, tradable=False),
    ).propose()

    assert watched == [SNAPSHOT, "headroom_usd", TRADABLE], watched
    assert watched.index(TRADABLE) > 0, (
        "the instrument must be able to observe a tradability read that is NOT "
        "first, or its verdict on the shipped module is unfalsifiable"
    )


def test_B1_the_LIVE_PASS_RUNS_FASTDROP_THEN_MIRROR_THEN_ARITHMETIC(
    watched: list[str],
) -> None:
    """The positive control: on a sizing pass the order is U1's order."""
    proposal = _go(_allocator(watched, _picture()))

    assert proposal.outcome is ProposalOutcome.SIZED, proposal
    assert watched[0] == TRADABLE, watched
    assert watched[1] == SNAPSHOT, watched
    assert set(watched[2:]) <= set(ARITHMETIC), watched
    assert len(watched) > 2, (
        "a pass that sized while calling NO arithmetic function would mean the "
        "recorders were never installed — the instrument, not the subject"
    )
    assert SNAPSHOT not in watched[2:], (
        "§3's atomicity rule: one pass reads ONE snapshot, so a second mirror "
        "read inside the arithmetic would be the torn read U2 exists to prevent"
    )


def test_B1_a_STALE_MIRROR_FAST_DROPS_AND_NEVER_SIZES(watched: list[str]) -> None:
    """§12.7: never size on a half-built mirror. Four non-FRESH states refuse."""
    for state in (MirrorState.EMPTY, MirrorState.PARTIAL, MirrorState.STALE):
        watched.clear()
        proposal = _go(_allocator(watched, _picture(), state=state))

        assert proposal.outcome is ProposalOutcome.STALE_MIRROR, (state, proposal)
        assert proposal.contracts == 0 and proposal.order is None, proposal
        assert not set(watched) & set(ARITHMETIC), (
            f"mirror state {state.value} sized anyway: {watched}"
        )
        assert state.value in proposal.reason, proposal.reason


def test_B1_the_PROPOSAL_NEVER_REACHES_A_BROKER_AND_NEVER_MUTATES_THE_PICTURE() -> None:
    """§2: permissive. The output is a proposal and the picture is read-only."""
    picture = _picture()
    proposal = _go(_allocator([], picture))

    assert proposal.reaches_broker is False, proposal
    assert proposal.order is not None and proposal.order.qty == proposal.contracts
    with pytest.raises(dataclasses.FrozenInstanceError):
        picture.balance = 1.0  # type: ignore[misc]
    assert picture.committed == 10_000.0, "the pass edited a published field"


# ==========================================================================
# B2 — HEADROOM = DEPLOYABLE_PCT x BALANCE - COMMITTED (§16 U2)
# ==========================================================================


def test_B2_headroom_USES_THE_PUBLISHED_COMMITTED_NOT_THE_SUM_OF_THE_ROWS() -> None:
    """THE PLANT: `committed` disagrees with the rows by $80,000, on purpose.

    §16 U2's correction is that the Allocator READS the Limiter's published
    figure. A sizer that re-derived `committed` from `positions` would produce
    a headroom of 70,000 − 90,000 here; one that reads produces 70,000 − 10,000.
    The two answers are 80,000 apart, so the measurement cannot be a coincidence.
    """
    rows = _rows(*([10_000.0] * 9))
    assert sum(row.margin for row in rows) == 90_000.0
    picture = _picture(committed=10_000.0, positions=rows)

    proposal = _go(_allocator([], picture))

    assert proposal.rationale.headroom == pytest.approx(0.70 * 100_000.0 - 10_000.0)
    assert proposal.rationale.headroom == pytest.approx(60_000.0), (
        "sizing used a `committed` this module derived rather than the one the "
        "Limiter published — §16 U2's single source of truth, lost"
    )


def test_B2_the_POSITION_TABLE_IS_NEVER_TRAVERSED() -> None:
    """§11.3's aggregates arrive precomputed; a correct pass never walks the rows."""
    _CountingPositions.traversals = 0
    picture = _picture(
        committed=10_000.0, positions=_CountingPositions(_rows(*([10_000.0] * 9)))
    )

    proposal = _go(_allocator([], picture))

    assert proposal.outcome is ProposalOutcome.SIZED, proposal
    assert _CountingPositions.traversals == 0, (
        f"the pass pulled {_CountingPositions.traversals} row(s) out of the "
        "position table — every figure it needs is a published aggregate"
    )


def test_B2_the_COUNTING_TABLE_ACTUALLY_COUNTS() -> None:
    """The falsifier for the arm above: an instrument that counts nothing passes it."""
    _CountingPositions.traversals = 0
    table = _CountingPositions(_rows(1.0, 2.0, 3.0))

    assert sum(row.margin for row in table) == 6.0
    assert _CountingPositions.traversals == 3, _CountingPositions.traversals


def test_B2_the_070_IS_READ_FROM_risks_AND_IS_NOT_CARVED_IN_THE_MODULE() -> None:
    """§12A:811 owns `DEPLOYABLE_PCT`; `risks/limiter.config.json` is its ONE home."""
    landed = json.loads((REPO / "risks" / "limiter.config.json").read_text("utf-8"))
    knobs = load_sizing_knobs(REPO)

    assert knobs.deployable_pct == landed["deployable_pct"], knobs
    assert knobs.deployable_pct == 0.70, (
        "the landed value drifted from §12A:811's stated default; this test "
        "reads the file rather than restating it, so it moves when the file does"
    )
    source = (REPO / "scripts" / "nixalloc" / "sizing.py").read_text("utf-8")
    for carved in ("0.70 *", "0.7 *", "* 0.70", "* 0.7"):
        assert carved not in source, (
            f"{carved!r} appears in sizing.py — a second authority for a number "
            "risks/limiter.config.json already owns"
        )


def test_B2_a_NEGATIVE_HEADROOM_CLAMPS_TO_ZERO_CONTRACTS_AND_IS_REPORTED() -> None:
    """§7:483 clamps ≥ 0; the negative headroom still reaches the audit record."""
    proposal = _go(_allocator([], _picture(committed=90_000.0)))

    assert proposal.rationale.headroom == pytest.approx(-20_000.0)
    assert proposal.rationale.margin_contracts == 0, proposal.rationale
    assert proposal.contracts == 0, proposal
    assert proposal.outcome is ProposalOutcome.ZERO_AFTER_CLAMP, proposal
    assert proposal.rationale.binding is BindingConstraint.HEADROOM, proposal.rationale


def test_B2_the_CONTENTION_POLICY_RECORDED_IS_ALWAYS_FCFS() -> None:
    """§6.6: no Scoring writer exists, so the fallback is the state we run in."""
    proposal = _go(_allocator([], _picture()))

    assert proposal.rationale.contention is ContentionPolicy.FCFS, proposal.rationale
    assert "correlation-bucket cap NOT APPLIED" in proposal.rationale.note, (
        "with no BucketCapPort wired, the rationale must SAY the §7 cap did not "
        "run — otherwise a green here would imply coverage this module lacks"
    )


# ==========================================================================
# B3 — SIZING GUARDS (§15 C3, §7) and §16 U4's single-instrument preference
# ==========================================================================


@pytest.mark.parametrize("stop_ticks", [0, -1, -50])
def test_B3_a_ZERO_OR_NEGATIVE_STOP_IS_A_DENY_SHAPED_NO_SIZE(stop_ticks: int) -> None:
    """§15 C3: the Limiter denies; the Allocator does not manufacture a size."""
    proposal = _go(_allocator([], _picture()), stop_ticks=stop_ticks)

    assert proposal.outcome is ProposalOutcome.NO_SIZE_DENY, proposal
    assert proposal.contracts == 0 and proposal.order is None, proposal
    assert "invalid stop intent" in proposal.reason, proposal.reason
    assert proposal.rationale.risk_contracts == 0, (
        "a NO-SIZE proposal must not carry a size nobody computed into §16 U5's "
        "audit record"
    )


def test_B3_a_SYMBOL_MISSING_FROM_THE_MARGIN_CACHE_IS_NOT_TRADABLE() -> None:
    """§7:483: missing margin ⇒ not-tradable, which is not the same as a deny."""
    proposal = _go(_allocator([], _picture(margins={"NQ": 100.0})))

    assert proposal.outcome is ProposalOutcome.NOT_TRADABLE, proposal
    assert "absent from the published margin cache" in proposal.reason, proposal.reason
    assert proposal.order is None, proposal


def test_B3_a_SYMBOL_WITH_NO_INSTRUMENT_SPEC_IS_NOT_TRADABLE() -> None:
    """No `tick_value` ⇒ the risk term is undefined ⇒ the same §7:483 posture."""
    proposal = _go(_allocator([], _picture(), instruments={}))

    assert proposal.outcome is ProposalOutcome.NOT_TRADABLE, proposal
    assert "no InstrumentSpec" in proposal.reason, proposal.reason


def test_B3_a_MICRO_LEG_ABSENT_FROM_THE_MARGIN_CACHE_IS_NOT_TRADABLE() -> None:
    """The selected instrument's own key must be published, not just its full."""
    proposal = _go(_allocator([], _picture(margins={"ES": 500.0})), stop_ticks=4)

    assert proposal.outcome is ProposalOutcome.NOT_TRADABLE, proposal
    assert "selected instrument MES" in proposal.reason, proposal.reason


def test_B3_the_SLIPPAGE_PAD_IS_INSIDE_THE_DOLLAR_RISK_FIGURE() -> None:
    """§7:481: `risk_$` is honest only if sized against stop + expected slippage.

    Driven as a DIFFERENCE, with both cases held on the SAME (micros) branch so
    the instrument-selection rule cannot be what moved the number. A module
    that ignored the pad would return the same count for both knob sets.
    """
    thin = _go(_allocator([], _picture(), knobs=_knobs(slippage_pad_ticks={"ES": 2})))
    wide = _go(_allocator([], _picture(), knobs=_knobs(slippage_pad_ticks={"ES": 4})))

    # micro tick value 1.25; risk-per-micro = (4 + pad) x 1.25
    assert thin.order is not None and thin.order.symbol == "MES", thin.order
    assert wide.order is not None and wide.order.symbol == "MES", wide.order
    assert thin.contracts == 13, thin  # floor(100 / 7.5)
    assert wide.contracts == 10, wide  # floor(100 / 10.0)
    assert thin.contracts != wide.contracts, (
        "the pad changed nothing — it is not inside the dollar-risk denominator"
    )


def test_B3_the_FULLS_BRANCH_of_the_single_instrument_rule_is_REACHED() -> None:
    """§7:492 / §16 U4: risk-ideal quantizes acceptably ⇒ FULLS ONLY.

    stop 2 + pad 2 = 4 ticks; micro tick value 1.25 ⇒ ideal = 20 micro units =
    exactly 2.0 fulls. 2 ≥ threshold 2 and quantization error 0.0 ≤ 0.25.
    """
    proposal = _go(_allocator([], _picture()), stop_ticks=2)

    assert proposal.outcome is ProposalOutcome.SIZED, proposal
    assert proposal.order is not None and proposal.order.symbol == "ES", proposal.order
    assert proposal.contracts == 2, proposal
    assert "fulls-only ES" in proposal.rationale.note, proposal.rationale.note
    assert proposal.order.margin_per_contract == 500.0, proposal.order


def test_B3_the_MICROS_BRANCH_of_the_single_instrument_rule_is_REACHED() -> None:
    """§7:492: 4 + 2 = 6 ticks ⇒ ideal = 13.33 micro units = 1.33 fulls < 2 ⇒ MICROS."""
    proposal = _go(_allocator([], _picture()), stop_ticks=4)

    assert proposal.outcome is ProposalOutcome.SIZED, proposal
    assert proposal.order is not None and proposal.order.symbol == "MES", proposal.order
    assert proposal.contracts == 13, proposal
    assert "micros-only MES" in proposal.rationale.note, proposal.rationale.note
    assert proposal.order.margin_per_contract == 50.0, proposal.order


def test_B3_the_QUANTIZATION_TOLERANCE_HALF_of_the_rule_is_LOAD_BEARING() -> None:
    """Both halves of §7:492 decide. Same input, tolerance alone flips the branch.

    stop 3 + pad 2 = 5 ticks ⇒ ideal = 16 micro units = 1.6 fulls. With
    threshold 1 the "≥ threshold fulls" half is satisfied either way, so the
    branch is decided by the 0.6 quantization error alone.
    """
    tight = _go(
        _allocator(
            [], _picture(), knobs=_knobs(micro_full_threshold=1, quant_tolerance=0.1)
        ),
        stop_ticks=3,
    )
    loose = _go(
        _allocator(
            [], _picture(), knobs=_knobs(micro_full_threshold=1, quant_tolerance=0.75)
        ),
        stop_ticks=3,
    )

    assert tight.order is not None and tight.order.symbol == "MES", tight.order
    assert loose.order is not None and loose.order.symbol == "ES", loose.order


def test_B3_a_PROPOSAL_IS_NEVER_A_MIXED_FULL_PLUS_MICRO_LEG() -> None:
    """§16 U4: one instrument per trade. The type makes it structural."""
    for stop in range(1, 40):
        proposal = _go(_allocator([], _picture()), stop_ticks=stop)
        if proposal.outcome is not ProposalOutcome.SIZED:
            continue
        assert proposal.order is not None
        assert proposal.order.symbol in ("ES", "MES"), proposal.order
        assert proposal.order.qty == proposal.contracts, proposal
        assert isinstance(proposal.order.qty, int) and proposal.order.qty > 0


def test_B3_the_SYMBOL_CAP_BINDS_AND_IS_NAMED_AS_THE_BINDING_CONSTRAINT() -> None:
    """§7:478's third term, and §16 U5's requirement that the rationale say so."""
    proposal = _go(_allocator([], _picture(), knobs=_knobs(symbol_cap={"ES": 1})))

    assert proposal.contracts == 10, proposal  # 1 full x 10 micro units
    assert proposal.rationale.binding is BindingConstraint.SYMBOL_CAP, proposal
    assert proposal.rationale.symbol_cap == 10, proposal.rationale


def test_B3_the_MARGIN_TERM_BINDS_WHEN_HEADROOM_IS_POSITIVE_BUT_THIN() -> None:
    """§7:477 with headroom above zero — MARGIN, not HEADROOM (§16 U5 precision)."""
    proposal = _go(_allocator([], _picture(balance=1_000.0, committed=500.0)))

    assert proposal.rationale.headroom == pytest.approx(200.0)
    assert proposal.rationale.margin_contracts == 4, proposal.rationale  # 200 / 50
    assert proposal.rationale.binding is BindingConstraint.MARGIN, proposal.rationale
    assert proposal.contracts == 4, proposal


def test_B3_EVERY_TERM_CLAMPS_AT_OR_ABOVE_ZERO() -> None:
    """§7:483: no negative-floor artifacts, on any input this pathway accepts."""
    for balance, committed, stop in (
        (0.0, 0.0, 1),
        (10.0, 1_000_000.0, 1),
        (5.0, 5.0, 3),
    ):
        proposal = _go(
            _allocator([], _picture(balance=balance, committed=committed)),
            stop_ticks=stop,
        )
        assert proposal.contracts >= 0, proposal
        assert proposal.rationale.risk_contracts >= 0, proposal.rationale
        assert proposal.rationale.margin_contracts >= 0, proposal.rationale
        assert proposal.rationale.symbol_cap >= 0, proposal.rationale


def test_B3_an_INVALID_KNOB_SET_IS_REFUSED_RATHER_THAN_DEFAULTED() -> None:
    """§12A:801: boot validation rejects an invalid set before anything registers."""
    for bad in (
        {"per_trade_risk_usd": 0.0},
        {"deployable_pct": 1.5},
        {"symbol_cap": {"ES": 0}},
        {"micro_full_threshold": 0},
        {"quant_tolerance": 1.0},
        {"slippage_pad_ticks": {"NQ": 2}},
    ):
        with pytest.raises(SizingConfigError):
            _knobs(**bad)


# ==========================================================================
# B4 — ONE VERSIONED ROW, READ BY BOTH THE ALLOCATOR AND THE REAL GATE (§6.4)
# ==========================================================================


class _RecordingPicture:
    """A pass-through over one `FinancialPicture` that logs every field read.

    Handed to BOTH readers so the comparison is over what each one actually
    observed, rather than over what this file believes it published.
    """

    def __init__(self, picture: FinancialPicture, sink: list[Any], reader: str) -> None:
        self._picture = picture
        self._sink = sink
        self._reader = reader

    def __getattr__(self, name: str) -> Any:
        value = getattr(self._picture, name)
        self._sink.append((self._reader, name, value))
        return value


class _Open:
    """A Phase-A flag port that blocks nothing. Symbol and global shapes both."""

    def read(self, *args: Any) -> tuple[bool, str]:
        """`(blocked, reason)` — never blocked, so Phase B is always reached."""
        del args
        return False, ""


class _Free:
    """The one-in-flight lock, held by nobody."""

    def in_flight(self, strategy_id: str) -> tuple[bool, str]:
        """`(locked, reason)`."""
        del strategy_id
        return False, ""


class _Solvent:
    """A fresh net-liq mark far above the §6.5 floor.

    Deliberately enormous. §5's fail-fast means the FIRST deny halts dispatch,
    so a survival floor that could bite on the inflated probe below would stop
    `DeployableCeilingRule` ever running — and that rule is the only one that
    reads the picture's VERSION STAMP, which is the field §6.4's identity claim
    is actually about.
    """

    def mark(self) -> tuple[float, bool]:
        """`(net_liq, fresh)`."""
        return 1e18, True


def _gate_pass() -> Any:
    """The REAL `nixrisk.gate.GatePass` over the REAL `default_manifest`.

    No ledger: §3's reservation is the Limiter's authority and taking one here
    would make this test a writer.
    """
    from nixrisk import gate  # pylint: disable=import-outside-toplevel

    class _Clear:
        """§11.5's HALT flag, clear — branch 0 must not short-circuit the pass."""

        def is_set(self) -> tuple[bool, str]:
            """`(halted, why)`."""
            return False, ""

    manifest = gate.default_manifest(
        blackout=_Open(),
        tradability=_Open(),
        staleness=_Open(),
        clock_skew=_Open(),
        in_flight=_Free(),
        net_liq=_Solvent(),
        deployable_fraction=0.70,
        survival_safety_pad=0.10,
        coherence_tolerance=0.01,
    )
    return gate, gate.GatePass(_Clear(), manifest, None)


def _both_readers(
    allocator_row: FinancialPicture, gate_row: FinancialPicture
) -> tuple[Any, Any, dict[str, dict[str, Any]]]:
    """Drive the Allocator and the REAL gate, recording every field each reads.

    The gate is driven TWICE against the same row: once with the order as
    sized, and once with an inflated quantity. §3's Phase B rules build their
    reason strings before branching, so the second pass is what makes the gate
    read `deployable` and the VERSION STAMP — and the version is the field the
    whole identity claim hangs on. One approving pass alone would leave `version`
    out of the shared set, which would have made this an identity claim about
    two fields neither reader stamps.
    """
    sink: list[Any] = []
    proposal = _go(_allocator([], _RecordingPicture(allocator_row, sink, "allocator")))
    assert proposal.outcome is ProposalOutcome.SIZED, proposal

    gate_mod, gate_pass = _gate_pass()
    outcome = gate_pass.evaluate(
        proposal.order, _RecordingPicture(gate_row, sink, "gate"), 1.5
    )
    gate_pass.evaluate(
        dataclasses.replace(proposal.order, qty=1_000_000),
        _RecordingPicture(gate_row, sink, "gate"),
        1.5,
    )

    seen: dict[str, dict[str, Any]] = {"allocator": {}, "gate": {}}
    for reader, field, value in sink:
        seen[reader].setdefault(field, value)
    return proposal, (gate_mod, outcome), seen


def test_B4_the_ALLOCATOR_AND_THE_REAL_GATE_OBSERVE_IDENTICAL_FIELD_VALUES() -> None:
    """§6.4: "the same versioned row ... identical bytes by construction".

    Measured, not reasoned: one picture, two readers, every read recorded with
    the reader's name, and every field BOTH read compared value-for-value. The
    non-vacuity floor is three shared fields — an identity claim over fewer is
    a claim about very nearly the empty set.
    """
    picture = _picture(balance=250_000.0, committed=20_000.0, version=903)
    proposal, (gate_mod, outcome), seen = _both_readers(picture, picture)
    shared = set(seen["allocator"]) & set(seen["gate"])

    assert len(shared) >= 3, (
        f"only {sorted(shared)} was read by both — an identity claim over fewer "
        "than three shared fields is a claim about the empty set"
    )
    assert {"balance", "committed", "version"} <= shared, sorted(shared)
    for field in sorted(shared):
        assert seen["allocator"][field] == seen["gate"][field], (
            f"{field}: allocator saw {seen['allocator'][field]!r}, the gate saw "
            f"{seen['gate'][field]!r} — one versioned row, two answers"
        )
    assert seen["allocator"]["version"] == seen["gate"]["version"] == 903
    assert outcome.decision is gate_mod.Decision.APPROVE, outcome
    assert proposal.rationale.snapshot_version == 903, proposal.rationale


def test_B4_the_COMPARISON_CATCHES_TWO_READERS_ON_DIFFERENT_VERSIONS() -> None:
    """THE FALSIFIER. Two pictures, and the same comparison must go red."""
    allocator_row = _picture(balance=250_000.0, committed=20_000.0, version=903)
    gate_row = _picture(balance=90_000.0, committed=20_000.0, version=904)

    _, _, seen = _both_readers(allocator_row, gate_row)
    shared = set(seen["allocator"]) & set(seen["gate"])
    disagreed = [f for f in shared if seen["allocator"][f] != seen["gate"][f]]

    assert "balance" in disagreed, (
        "the instrument did not notice two readers on two different rows, so "
        "its agreement verdict above proves nothing"
    )
    assert "version" in disagreed, (
        f"the version stamp itself was not compared ({sorted(shared)}) — §6.4's "
        "'same versioned row' is exactly the claim this instrument must be able "
        "to refute"
    )


def test_B4_THE_GAP_the_gate_reads_MARGIN_FROM_THE_ORDER_not_from_the_picture() -> None:
    """Named rather than papered over: `margin_per_contract` crosses on the ORDER.

    `AggregateMarginCapRule` and `DeployableCeilingRule` both divide by
    `order.margin_per_contract`, never `picture.margin_per_contract` — so for
    that ONE field the identity is carried by the Allocator's copy rather than
    by both readers touching the same row. The strongest provable statement is
    that the copy equals the published row at the version the Allocator sized
    against, and that is what this asserts.
    """
    source = (REPO / "scripts" / "nixrisk" / "gate.py").read_text("utf-8")
    assert "order.margin_per_contract" in source, (
        "the gap this test names is gone from gate.py — re-derive the claim"
    )
    assert "picture.margin_per_contract" not in source, (
        "the gate now reads margin from the PICTURE; this test's premise has "
        "changed and the weaker claim below is no longer the strongest one"
    )

    picture = _picture(version=903)
    proposal = _go(_allocator([], picture))

    assert proposal.order is not None
    assert (
        proposal.order.margin_per_contract
        == picture.margin_per_contract[proposal.order.symbol]
    ), proposal.order
    assert proposal.rationale.snapshot_version == picture.version


def test_B4_the_ORDER_ID_NAMES_THE_VERSION_IT_WAS_SIZED_AGAINST() -> None:
    """§9's replay needs a deterministic id; §16 U5's audit needs the version."""
    picture = _picture(version=903)
    first = _go(_allocator([], picture))
    second = _go(_allocator([], picture))

    assert first.order is not None and second.order is not None
    assert first.order.client_order_id == second.order.client_order_id
    assert "v903" in first.order.client_order_id, first.order.client_order_id


def test_B4_the_ALLOCATOR_SATISFIES_THE_FROZEN_AllocatorPort_VERB_SET() -> None:
    """`AllocatorPort` is not runtime_checkable, so the verb set is asserted here."""
    allocator = _allocator([], _picture())

    assert callable(allocator.propose)
    for forbidden in ("publish", "reserve", "place", "commit", "set", "update"):
        assert not hasattr(allocator, forbidden), (
            f"§2: the Allocator grew a {forbidden!r} verb — authority it does not have"
        )
