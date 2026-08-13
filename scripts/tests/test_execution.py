"""ARC 029 / Stage 2.3 — the idempotent execution ledger, driven directly.

This is `nixrisk.execution`'s own can-fail suite. It owns §4's idempotency
PROPERTY — that position state is a function of the SET of unique
`(order_id, exec_id)` fills, and so is unchanged by duplicate or out-of-order
delivery — plus the fail-closed refusal of a contradictory duplicate.

**Every control asserts the REASON** — the message, the field, or the arithmetic
— never the exception type alone (check contract v2 §11).

§7.12, THE STANDING QUESTION — *what would make this pass while measuring nothing?*
The brief's own hypothesis names it: **a dedup test that never delivers a duplicate
measures nothing.** A stream of unique, in-order reports cannot tell a correct
ledger from one that forgot to deduplicate — both produce the same answer on it. So
this file NEVER rests the idempotency verdict on a clean stream. It:

  * delivers duplicates AND out-of-order reports and proves the derived position is
    unchanged (`test_position_is_INVARIANT_under_every_permutation_and_duplication`);
  * MEASURES the hypothesis directly against a dedup-less naive counter — the clean
    stream cannot distinguish it from the correct ledger, the dirty stream can — so
    the vacuity is demonstrated, not merely asserted
    (`test_the_HYPOTHESIS__a_clean_stream_cannot_tell_the_defect_apart`);
  * asserts non-vacuity structurally: the permutations really are reordered and the
    duplicated streams really are longer than the unique set.
"""
# pylint: disable=invalid-name,redefined-outer-name,protected-access

from __future__ import annotations

import itertools
from collections.abc import Sequence

import pytest  # pylint: disable=import-error
from nixrisk.execution import (
    ContradictoryExecution,
    DerivedPosition,
    ExecutionLedger,
    ExecutionReport,
    FillSide,
    IngestDisposition,
    InvalidExecutionReport,
    OrderAudit,
)
from nixrisk.seam import PositionRow, PositionState

# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def fill(  # pylint: disable=too-many-arguments
    order_id: str,
    exec_id: str,
    symbol: str,
    filled_qty: int,
    cumulative_qty: int,
    *,
    side: FillSide = FillSide.BUY,
    price: float = 5000.25,
    ts: float = 1000.0,
) -> ExecutionReport:
    """One execution report with a non-round positive price by default."""
    return ExecutionReport(
        order_id=order_id,
        exec_id=exec_id,
        symbol=symbol,
        side=side,
        filled_qty=filled_qty,
        price=price,
        cumulative_qty=cumulative_qty,
        ts=ts,
    )


#: A canonical multi-order, multi-symbol, entry-and-exit fill SET. Two BUY orders
#: open positions in two instruments; one SELL order partly closes the first. Every
#: figure below is hand-computed so the reference is pinned to arithmetic, not merely
#: self-consistent:
#:   ESZ6 net = (2+2+1 bought) − 1 sold = 4 ; NQZ6 net = 1+3 = 4
#:   order O-1 cumulative = 5 ; O-2 = 4 ; O-3 = 1
CANONICAL: tuple[ExecutionReport, ...] = (
    fill("O-1", "e1", "ESZ6", 2, 2),
    fill("O-1", "e2", "ESZ6", 2, 4),
    fill("O-1", "e3", "ESZ6", 1, 5),
    fill("O-2", "e1", "NQZ6", 1, 1),
    fill("O-2", "e2", "NQZ6", 3, 4),
    fill("O-3", "e1", "ESZ6", 1, 1, side=FillSide.SELL, price=5010.75),
)
_ESZ6_NET = 4
_NQZ6_NET = 4


def fed(reports: Sequence[ExecutionReport]) -> ExecutionLedger:
    """A fresh ledger fed the stream in the given arrival order."""
    ledger = ExecutionLedger()
    ledger.ingest_all(reports)
    return ledger


def snapshot(ledger: ExecutionLedger) -> dict[str, DerivedPosition]:
    """The full derived position state, keyed by symbol — the thing that must be
    invariant across permutation and duplication."""
    return {sym: ledger.position(sym) for sym in sorted(ledger.symbols())}


# ---------------------------------------------------------------------------
# The reference — pinned to hand-computed arithmetic, not self-consistency
# ---------------------------------------------------------------------------


def test_the_REFERENCE_position_matches_HAND_COMPUTED_values() -> None:
    """A permutation test that only proves 'all orders agree with each other' is
    vacuous if the agreed value is wrong. This pins the reference to arithmetic."""
    ledger = fed(CANONICAL)
    esz6 = ledger.position("ESZ6")
    nqz6 = ledger.position("NQZ6")

    assert esz6.net_qty == _ESZ6_NET, esz6
    assert esz6.bought_qty == 5 and esz6.sold_qty == 1, esz6
    assert nqz6.net_qty == _NQZ6_NET, nqz6
    assert ledger.order_cumulative("O-1") == 5
    assert ledger.order_cumulative("O-2") == 4
    assert ledger.fill_count() == 6


# ---------------------------------------------------------------------------
# §4 — THE IDEMPOTENCY PROPERTY: a function of the SET, under any permutation
# and duplication
# ---------------------------------------------------------------------------


def _duplicated(stream: Sequence[ExecutionReport]) -> list[ExecutionReport]:
    """Every report delivered twice, interleaved: report, its copy, next... A
    maximally-duplicated stream, so the dedup path is exercised on every key."""
    doubled: list[ExecutionReport] = []
    for report in stream:
        doubled.append(report)
        doubled.append(report)
    return doubled


def test_position_is_INVARIANT_under_every_permutation_and_duplication() -> None:
    """THE FLAGSHIP. §4: position derives from cumulative fills, immune to duplicate
    OR out-of-order execution reports.

    Fresh ledgers are fed every permutation of the canonical set (order-independence)
    and every permutation with every report duplicated (duplicate-immunity), and each
    must reproduce the reference snapshot EXACTLY. A subset of permutations is used
    (deterministic sampling, not randomness — no flake) but it provably includes
    reordered and reversed streams.

    §7.12 non-vacuity is asserted, not assumed: at least one delivered stream is out
    of natural order, and every duplicated stream is strictly longer than the unique
    set while yielding the identical position — which is exactly what a stream that
    'never delivers a duplicate' could not show.
    """
    reference = snapshot(fed(CANONICAL))
    assert reference["ESZ6"].net_qty == _ESZ6_NET  # guard the reference itself

    # Deterministic sample of permutations: every 7th of the 720, plus the reverse.
    all_perms = list(itertools.permutations(CANONICAL))
    perms = all_perms[::7] + [tuple(reversed(CANONICAL))]

    saw_reordered = False
    saw_longer_dirty_stream = False
    for perm in perms:
        if list(perm) != list(CANONICAL):
            saw_reordered = True

        clean_ledger = fed(perm)
        assert snapshot(clean_ledger) == reference, (
            f"permutation changed the position: {perm}"
        )
        # The reordering must have been REAL work, not a no-op: every unique key is
        # still present exactly once regardless of arrival order.
        assert clean_ledger.fill_count() == len(CANONICAL)

        dirty = _duplicated(perm)
        dirty_ledger = fed(dirty)
        if len(dirty) > len(CANONICAL):
            saw_longer_dirty_stream = True
        assert snapshot(dirty_ledger) == reference, (
            f"duplication changed the position: len(stream)={len(dirty)}"
        )
        assert dirty_ledger.fill_count() == len(CANONICAL)
        assert dirty_ledger.duplicates == len(CANONICAL)

    assert saw_reordered, "vacuous: no delivered stream was actually reordered"
    assert saw_longer_dirty_stream, "vacuous: no duplicated stream was longer"


def test_the_HYPOTHESIS__a_clean_stream_cannot_tell_the_defect_apart() -> None:
    """The brief's stated hypothesis, MEASURED rather than assumed.

    The planted defect is `_naive_net`: a position accumulator that FORGOT to
    deduplicate — it sums signed quantity over the raw stream. Against a clean,
    unique stream it agrees with the correct ledger, so a dedup test built on a clean
    stream measures nothing: it cannot redden on the defect. Against a stream
    carrying duplicates the defect double-counts and diverges, so the duplicate is
    what makes the measurement real. This is the can-fail: the defect is GREEN on the
    vacuous input and RED on the meaningful one.
    """

    def _naive_net(stream: Sequence[ExecutionReport], symbol: str) -> int:
        """The dedup-less defect: no `(order_id, exec_id)` key, just a running sum."""
        return sum(r.signed_qty for r in stream if r.symbol == symbol)

    clean = list(CANONICAL)
    dirty = _duplicated(CANONICAL)
    correct = fed(dirty).position("ESZ6").net_qty

    # The correct ledger is immune to the duplicates.
    assert correct == _ESZ6_NET
    assert fed(clean).position("ESZ6").net_qty == _ESZ6_NET

    # The defect is INDISTINGUISHABLE from correct on the clean stream — the vacuity.
    assert _naive_net(clean, "ESZ6") == correct, (
        "a clean stream cannot separate a correct ledger from a dedup-less one"
    )
    # The defect is VISIBLE on the dirty stream — the measurement the brief demands.
    assert _naive_net(dirty, "ESZ6") != correct, (
        "the duplicated stream must expose the dedup-less defect, or it too is vacuous"
    )
    assert _naive_net(dirty, "ESZ6") == 2 * _ESZ6_NET  # every signed fill counted twice


def test_a_pure_re_delivery_is_a_NO_OP_and_is_counted() -> None:
    """An exact re-delivery of a seen key changes nothing and is reported DUPLICATE,
    so a caller can see the idempotency fired rather than infer it from silence."""
    ledger = ExecutionLedger()
    first = ledger.ingest(CANONICAL[0])
    before = ledger.position("ESZ6")

    second = ledger.ingest(CANONICAL[0])

    assert first.disposition is IngestDisposition.APPLIED
    assert second.disposition is IngestDisposition.DUPLICATE
    assert not second.applied
    assert ledger.position("ESZ6") == before, "a duplicate moved the position"
    assert ledger.applied == 1 and ledger.duplicates == 1
    assert ledger.fill_count() == 1


def test_OUT_OF_ORDER_delivery_alone_leaves_cumulative_and_position_correct() -> None:
    """Out-of-order isolated from duplication: the three execs of one order arrive
    last-first. Cumulative and net must be right, and the stream must really be
    reversed (else the test proves nothing)."""
    order = (CANONICAL[0], CANONICAL[1], CANONICAL[2])
    reversed_stream = tuple(reversed(order))
    assert reversed_stream != order  # non-vacuity: it is actually out of order

    ledger = fed(reversed_stream)

    assert ledger.order_cumulative("O-1") == 5
    assert ledger.position("ESZ6").net_qty == 5
    assert ledger.audit("O-1").complete


# ---------------------------------------------------------------------------
# FAIL CLOSED — a contradictory duplicate is not a benign duplicate
# ---------------------------------------------------------------------------


def test_a_CONTRADICTORY_DUPLICATE_fails_closed_and_NAMES_the_field() -> None:
    """A second report under a seen `(order_id, exec_id)` with a different quantity
    is a broker inconsistency. It must RAISE — naming the field and the values — and
    must neither overwrite nor be silently dropped. The can-fail is built in: we show
    a last-write-wins ledger WOULD have changed the position, so the refusal is
    guarding a real difference, not a formality."""
    ledger = ExecutionLedger()
    ledger.ingest(fill("O-9", "x1", "ESZ6", 2, 2))
    before = ledger.position("ESZ6")
    contradiction = fill("O-9", "x1", "ESZ6", 7, 7)  # same key, different qty

    with pytest.raises(ContradictoryExecution) as caught:
        ledger.ingest(contradiction)

    msg = str(caught.value)
    assert "filled_qty: 2 then 7" in msg, msg
    assert "('O-9', 'x1')" in msg, msg
    assert "not a rewrite" in msg, msg
    # Neither overwritten nor dropped-into-nothing: state is exactly as before.
    assert ledger.position("ESZ6") == before
    assert ledger.contradictions == 1 and ledger.duplicates == 0
    # The difference was real: a last-write-wins ledger would have diverged.
    assert contradiction.signed_qty != before.net_qty


def test_a_CONTRADICTORY_PRICE_under_a_seen_key_also_fails_closed() -> None:
    """The contradiction check is over identity fields, not qty alone: a re-priced
    duplicate is the same class of broker inconsistency."""
    ledger = ExecutionLedger()
    ledger.ingest(fill("O-9", "x1", "ESZ6", 2, 2, price=5000.25))

    with pytest.raises(ContradictoryExecution) as caught:
        ledger.ingest(fill("O-9", "x1", "ESZ6", 2, 2, price=4999.75))

    assert "price: 5000.25 then 4999.75" in str(caught.value), str(caught.value)


def test_a_SIDE_FLIP_within_one_order_fails_closed() -> None:
    """One order_id is one direction. A new exec that flips side is refused, naming
    both sides — a BUY order does not sell."""
    ledger = ExecutionLedger()
    ledger.ingest(fill("O-9", "x1", "ESZ6", 2, 2, side=FillSide.BUY))

    with pytest.raises(ContradictoryExecution) as caught:
        ledger.ingest(fill("O-9", "x2", "ESZ6", 1, 3, side=FillSide.SELL))

    assert "already filled buy" in str(caught.value), str(caught.value)
    assert "reports sell" in str(caught.value), str(caught.value)
    assert ledger.contradictions == 1


def test_a_SYMBOL_SWAP_within_one_order_fails_closed() -> None:
    """One order_id is one instrument. A new exec in a different symbol is refused."""
    ledger = ExecutionLedger()
    ledger.ingest(fill("O-9", "x1", "ESZ6", 2, 2))

    with pytest.raises(ContradictoryExecution) as caught:
        ledger.ingest(fill("O-9", "x2", "NQZ6", 1, 3))

    assert "already filled 'ESZ6'" in str(caught.value), str(caught.value)
    assert "reports 'NQZ6'" in str(caught.value), str(caught.value)
    assert "one order is one" in str(caught.value), str(caught.value)


# ---------------------------------------------------------------------------
# §4 CUMULATIVE CROSS-CHECK — the derived total vs the broker's reported one
# ---------------------------------------------------------------------------


def test_AUDIT_detects_a_MISSING_exec_via_the_cumulative_crosscheck() -> None:
    """The broker's `cumulative_qty` is an INDEPENDENT record of how much filled. A
    gap between it and the derived Σ of increments is a missing exec — detectable
    even though the fills that DID arrive came out of order. This is why the report
    carries the broker cumulative at all."""
    # e2 (the middle increment) is never delivered; e3 reports cumulative 5.
    ledger = fed((CANONICAL[2], CANONICAL[0]))  # e3 then e1, out of order, e2 absent

    audit = ledger.audit("O-1")

    assert isinstance(audit, OrderAudit)
    assert audit.derived_cumulative == 3, audit  # 1 (e3) + 2 (e1)
    assert audit.reported_cumulative == 5, audit  # max cumulative_qty seen
    assert audit.gap == 2, audit
    assert not audit.complete
    # Can-fail direction: the COMPLETE set closes the gap.
    assert fed((CANONICAL[0], CANONICAL[1], CANONICAL[2])).audit("O-1").complete


# ---------------------------------------------------------------------------
# RECONCILIATION against §3's published position row
# ---------------------------------------------------------------------------


def row(symbol: str, size: int) -> PositionRow:
    """One §3 position-table row, size assumed SIGNED (see execution.py)."""
    return PositionRow(
        trade_id=f"T-{symbol}",
        symbol=symbol,
        strategy_id="strat-1",
        size=size,
        margin=1234.5,
        state=PositionState.OPEN,
    )


def test_RECONCILE_agrees_when_the_row_matches_and_flags_drift_when_it_does_not() -> (
    None
):
    """Both directions, so the control can redden: a matching signed row agrees; a
    wrong row is flagged with the exact derived-vs-row numbers. A reconcile that only
    ever saw agreement could not tell the two apart."""
    ledger = fed(CANONICAL)

    good = ledger.reconcile([row("ESZ6", _ESZ6_NET), row("NQZ6", _NQZ6_NET)])
    assert all(d.agrees for d in good), good

    bad = ledger.reconcile([row("ESZ6", _ESZ6_NET - 1), row("NQZ6", _NQZ6_NET)])
    esz6 = next(d for d in bad if d.symbol == "ESZ6")
    assert not esz6.agrees
    assert esz6.derived_net_qty == _ESZ6_NET and esz6.row_size == _ESZ6_NET - 1
    assert esz6.drift == 1, esz6


def test_RECONCILE_surfaces_a_position_no_row_shows() -> None:
    """A fill ledger holding a symbol the position table omits is drift, not silence
    — the exact signature of a fill applied to a position that was never opened in
    the table."""
    ledger = fed(CANONICAL)

    drifts = ledger.reconcile([row("ESZ6", _ESZ6_NET)])  # NQZ6 row missing

    nqz6 = next(d for d in drifts if d.symbol == "NQZ6")
    assert nqz6.row_size == 0 and nqz6.derived_net_qty == _NQZ6_NET
    assert not nqz6.agrees


# ---------------------------------------------------------------------------
# INGRESS GUARDS — a report that is not a possible execution is refused
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("qty", "cumulative", "reason"),
    [
        (0, 0, "filled_qty=0"),
        (-1, 5, "filled_qty=-1"),
        (5, 4, "cumulative_qty=4"),  # cumulative below this increment
    ],
)
def test_a_report_with_impossible_QUANTITIES_is_refused_at_construction(
    qty: int, cumulative: int, reason: str
) -> None:
    """A zero/negative increment is a fill no arithmetic can see; a cumulative below
    its own increment is not a running total. Refused at construction, with reason."""
    with pytest.raises(InvalidExecutionReport) as caught:
        fill("O-1", "e1", "ESZ6", qty, cumulative)

    assert reason in str(caught.value), str(caught.value)


@pytest.mark.parametrize("price", [0.0, -1.0, float("inf"), float("nan")])
def test_a_report_with_a_NON_POSITIVE_or_NON_FINITE_price_is_refused(
    price: float,
) -> None:
    """A fill priced at zero/NaN/Inf poisons every VWAP it enters."""
    with pytest.raises(InvalidExecutionReport) as caught:
        fill("O-1", "e1", "ESZ6", 1, 1, price=price)

    assert "is not a finite positive figure" in str(caught.value), str(caught.value)


@pytest.mark.parametrize("blank", ["order_id", "exec_id", "symbol"])
def test_a_report_with_a_BLANK_KEY_FIELD_is_refused(blank: str) -> None:
    """A blank order_id/exec_id/symbol would collide unrelated fills into one key."""
    kwargs = {"order_id": "O-1", "exec_id": "e1", "symbol": "ESZ6"}
    kwargs[blank] = ""
    with pytest.raises(InvalidExecutionReport) as caught:
        fill(**kwargs, filled_qty=1, cumulative_qty=1)  # type: ignore[arg-type]

    assert f"{blank} is empty" in str(caught.value), str(caught.value)


# ---------------------------------------------------------------------------
# The ledger is SYNCHRONOUS — §5's single-threaded loop
# ---------------------------------------------------------------------------


def test_the_LEDGER_is_SYNCHRONOUS_on_every_verb() -> None:
    """§5 fixes the Limiter as a single-threaded loop; an awaitable `ingest` would
    admit a second pass reading a position that does not yet include a delivered
    fill — the fill-vs-tick race §5 eliminates by construction."""
    import inspect  # pylint: disable=import-outside-toplevel

    for name in ("ingest", "ingest_all", "position", "audit", "reconcile"):
        verb = getattr(ExecutionLedger, name)
        assert not inspect.iscoroutinefunction(verb), (
            f"{name} is a coroutine — §5's single-threaded posture forbids it"
        )
