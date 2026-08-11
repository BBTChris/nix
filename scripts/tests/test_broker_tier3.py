"""
test_broker_tier3.py — TIER-3 TRAVERSAL of the IBKR broker-order adapter (debug.md §5).

This is a DISCOVERY instrument, not a regression suite. `test_broker_order.py` already owns
the per-behaviour properties of this adapter (Tier 2: did this change break something).
This file owns a property that file does not assert and structurally cannot: **what the
module does across its pathways, in combination, in the order a real caller would use
them** — debug.md §5.1's "the sequences nobody designs for: the same operation twice,
operations interleaved, an operation retried after a partial failure, a caller that
abandons midway."

VERIFY-AND-CHECKS Part C.9 ("extend an instrument that already owns a property; never
build a second") was considered and is satisfied by that boundary: no assertion below
duplicates one in `test_broker_order.py`. The one shared artefact — `FakeIB` — is
IMPORTED, not copied, for exactly the C.9 reason: two fakes would drift and a traversal
driven against a drifted fake measures a venue that does not exist. `_FIDELITY` below
asserts the imported fake still carries the surface these traversals drive, so drift
fails loudly instead of silently narrowing scope.

WHAT A FINDING LOOKS LIKE HERE. Three encodings, used deliberately:

  1. `@pytest.mark.xfail(strict=True)` — the spec DOES determine the outcome and the
     adapter violates it. strict, so the day someone repairs it the suite goes RED and
     the debt row has to be closed rather than quietly rotting. An xfail here is a
     CODE DEFECT with a name.
  2. A plain assertion on a DERIVED relation — the behaviour is defined, correct, and
     the traversal proves it holds under interleaving.
  3. A plain assertion on observed behaviour plus `SPEC GAP` in the docstring — the
     spec does not determine the answer. Per the ARC 019 brief §5/B2 the correct output
     is the finding and the section that would have to say, NOT an invented invariant.
     Nothing below encodes an invented answer as an assertion.

CITATIONS. Every § below was resolved against the real document before it was written
(ARC 019 §0a). Verified anchors, at commit 8cdfdcb:
  - `nics_risk_subsystem_spec_v1.3.md` §2A  — line 53, "Broker Abstraction Contract"
  - §2A's numbered seam invariants 1-5      — lines 103-108 (NOT §14; §14 is unnumbered)
  - §2A `query_order_status ... never auto-resend` — line 71
  - §4 "State Model"                        — line 178
  - §4 "Boot / known-state discipline"      — a real bold heading inside §4
  - §4 "Partial fill (v1.3, locked)"        — a real bold heading inside §4
  - §13 "CC Verification Objectives"        — line 891; items 9, 11, 22 are numbered
    plainly (`9.`, `11.`, `22.`), NOT `V9`/`V11`/`V22`. The `V` prefix begins at V24.
  - §14 "Locked Invariants (do not violate)" — line 965, unnumbered bullets
  - debug.md §5 Tier-3, §5.3 bounds, §5.4 scale, §5.5 corner cases, §7.4, §7.9, §7.12,
    failure modes #11 and #14 — all real headings in debug.md v1.2.0.
NOT USED anywhere below: `§2.1`, which ARC 018 established does not exist.

--------------------------------------------------------------------------------------
debug.md §7.12 — THE STANDING QUESTION, answered in writing, for this suite as a whole.

  "What would have to be true for `test_broker_tier3.py` to pass while measuring
   nothing?"

Six conditions, every one of them plantable:

  V1. THE INTERLEAVING NEVER HAPPENS. This is the characteristic vacuity of a
      concurrency suite and it is invisible: a test that schedules two tasks and awaits
      them proves nothing if the second ran only after the first had fully finished in a
      way the assertions cannot distinguish. PLANT: delete the `await` that releases a
      gate Event and the traversal still ends in the same terminal state. DEFENCE: every
      sequence asserts on an ORDERING or on a mid-flight SAMPLE, never on the end state
      alone, and each carries an explicit `nonvac(...)` call whose failure message says
      the interleaving did not occur.
  V2. THE FAKE STOPS CARRYING THE SURFACE. `FakeIB` lives in `test_broker_order.py`,
      which sub-agent A owns and is editing concurrently. If `reqpos_calls`,
      `historical_executions` or `push_exec` were renamed, these drivers would degrade
      to "the adapter was never actually driven". PLANT: rename one. DEFENCE: `_FIDELITY`
      is asserted at module import.
  V3. THE ADAPTER NEVER REACHED THE STATE UNDER TEST. Several sequences depend on being
      INSIDE a window — the startup gate closed, the mirror rebuild pending. PLANT: move
      the gate Event release one line earlier and the window closes before the traversal
      enters it. DEFENCE: each such test asserts the window's own flags
      (`_startup_complete`, `_connected`, `_mirror_rebuilds`, `reqpos_calls`) at the
      instant it claims to be inside.
  V4. THE SINK IS NOT THE ONE THE ADAPTER WRITES TO. This is §7.12's own eighth
      instance, found in ARC 016: assertions read a `RecordingSink` nothing had written
      to. PLANT: construct the adapter with one sink and assert on another. DEFENCE:
      `new_ad()` is the only construction path and returns the same object it injected;
      every sequence asserts something non-empty on that sink before drawing a
      conclusion from an emptiness.
  V5. THE ORDERING OBSERVABLE IS CID-BLIND. `RecordingSink.sequence` records event NAMES
      only, so "the ack preceded the fill" can be asked of a stream containing exactly
      one order and of no other. With two orders in flight it cannot express the
      question at all. PLANT: read `sink.sequence` instead of `sink.ordered`. DEFENCE:
      `test_control_cid_blind_ordering_is_blind` is the CONTROL — it demonstrates
      structurally that the blind log carries no identity, and behaviourally that it
      MISSES a violation the cid-tagged log catches.
  V6. AN xfail SILENTLY BECOMES AN xpass. A finding that got fixed while its marker
      stayed would leave a permanently-green marker measuring nothing. PLANT: fix any
      one defect below. DEFENCE: every xfail is `strict=True`, so an xpass is a FAILURE.
      STATUS AFTER ARC 020: this file now carries ZERO xfail markers — all five were
      removed, each in the same motion as the fix it marked (T3-01/A2, T3-01b/A1,
      T3-02/A1, T3-02b/A3, T3-10/A5). The defence WORKED and is recorded rather than
      deleted: every one of the five turned the suite RED as an xpass the moment its
      repair landed, which is exactly what forced the assertion to be inverted instead of
      the marker quietly rotting. The count is DERIVED from the suite, never asserted
      against an expectation — see the arc report.

  V7. AN INVERTED ASSERTION MEASURES THE OPPOSITE OF NOTHING (new, ARC 020). Five
      assertions in this file were inverted when their findings were repaired or ruled on.
      An inversion is the moment a traversal is most likely to become one-sided: T7 could
      assert "the ack was admitted" without ever proving anything is still refused, and a
      gate that admits everything would pass. PLANT: delete the refusal half of T7, or the
      "emits again after expiry" half of T1b. DEFENCE: every inverted traversal asserts
      BOTH directions — an admission AND a refusal (T7), suppression AND expiry (T1/T1b),
      indeterminate AND unknown AND working (T5b), a refused cancel AND a working one
      (T10), no publish over a dead session AND a publish over a live one (T11).

CAN-FAIL EVIDENCE, with CONTROL (debug.md §7.1) — recorded here rather than in an arc
report, because the next person to edit this file is the one who needs it.

  THE CONTROL, planted ARC 019 at 8cdfdcb. `ack_before_fill_violations` is the checker
  the whole ordering claim rests on. Plant: `if ack is None or ack > idx` -> `and`, a
  one-token swap that makes the checker structurally unable to report a violation.
    - PLANTED   -> `test_control_cid_blind_ordering_is_blind` FAILED, naming the site:
                   `scripts/tests/test_broker_tier3.py:376`, `assert [] == ['b']`.
    - AND THE POINT: under the same plant, `test_t3_...` and `test_t9_...` — the two
      traversals that USE the checker — both still PASSED, because they assert `== []`
      and a checker that never fires satisfies that trivially. A suite without this
      control would have gone green over a dead checker. That is failure mode #1
      (instrument stopped perturbing) and it is why the control is a test and not a note.
    - UNPLANTED -> control PASSES; file sha256 f1926f94acbe4b01…4cb03864bc, byte-identical
      to the pre-plant copy. `__pycache__` purged between every step (ARC 018 proved a
      pure line swap preserves both byte size and integer-second mtime).

  THE NON-VACUITY GUARDS, demonstrated WITHOUT a plant, which is stronger. Two `nonvac()`
  calls fired for real during construction and named the exact defect in the driver:
    - `test_t9_...` — "the two orders' event streams never interleaved", printing the
      observed stream. The first drive completed order A entirely before B began, so the
      test would have asserted a per-identity ordering guarantee over a sequence that
      never interleaved. The guard caught it; the drive was rewritten.
    - `test_t6_...` — "the venue call was never entered", because `GatedIB` inherits
      `reqpos_calls` from the fake it wraps and connect()'s own rebuild had already
      consumed one. The literal `== 1` was replaced by a baseline derived at runtime
      (§7.4). Both are recorded because an instrument that has been seen to fire is worth
      more than one that has only been reasoned about.

WHAT THIS SUITE STILL CANNOT MEASURE, stated rather than left to be found:
  - Anything cross-THREAD. This adapter runs on one asyncio loop and several sequences
    below are unreachable there precisely because the loop is single-threaded. Those are
    asserted as ATOMICITY, with the would-be racer proven to have been scheduled and to
    have stayed pending. If a thread is ever added to this module the proofs invert and
    this file must be re-read, not re-run.
  - Real socket behaviour. Everything here is against a declared stand-in (debug.md
    failure mode #12: record the environment in the evidence itself). Nothing below is
    a claim about IBKR.
  - Whether the module is FIT FOR PURPOSE in the §5.2 sense. That needs the Limiter,
    which does not exist. Only the §5.1/§5.3/§5.4/§5.5 halves of Tier 3 are attempted.
--------------------------------------------------------------------------------------
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# pylint suppressions for THIS FILE, each with its reason. Named codes only.
#
#   invalid-name
#       The fake mirrors ib_async's real surface (reqPositionsAsync, placeOrder,
#       orderStatusEvent). Renaming to snake_case would stop it standing in for
#       the thing it fakes.
#   protected-access
#       The traversals read ad._mirror, ad._from_ib, ad._startup_complete,
#       ad._connected, ad._orders. Those ARE the subject: a Tier-3 traversal of a
#       concurrency defect has to observe the state mid-flight, and inferring it
#       from an output is exactly the indirection CLAUDE.md directive 2 forbids.
#   missing-function-docstring / missing-class-docstring
#       Only on tiny local helpers; every test carries a full docstring.
#   unused-argument
#       Fake vendor methods must accept the arguments the real ones take.
#   too-many-* / too-many-lines
#       A traversal suite's size IS its coverage, and each finding's reasoning is
#       load-bearing evidence for a triage decision the parent has to make.
#   duplicate-code
#       Setup preambles are intentionally identical across sequences so the
#       DIFFERENCE between two traversals is the sequence and nothing else.
#   too-many-arguments / too-many-positional-arguments
#       OrderedSink.on_fill's six parameters are fixed by §2A's on_fill event,
#       not by this file. The metric is measuring the contract.
#   super-init-not-called
#       GatedIB copies the inner FakeIB's __dict__ on purpose — it must BE the
#       same fake mid-scenario, not a fresh one. Same pattern, and the same
#       reason, as RacingIB in test_broker_order.py.
#   use-implicit-booleaness-not-comparison
#       `x == []` is deliberate where the assertion is "this list is empty AND
#       it is a list". A falsiness test would also pass on None, which is what
#       a mistyped observable returns, and a traversal that cannot tell "no
#       violations" from "no observable" is exactly §7.12's failure family.
# pylint: disable=invalid-name,protected-access,missing-function-docstring
# pylint: disable=missing-class-docstring,unused-argument,too-many-locals
# pylint: disable=too-many-statements,too-many-lines,duplicate-code
# pylint: disable=too-many-arguments,too-many-positional-arguments
# pylint: disable=super-init-not-called,use-implicit-booleaness-not-comparison
import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field

import pytest  # pylint: disable=import-error
from broker_order_ibkr import IBKRBrokerOrder
from broker_seam import (
    BrokerNotConnected,
    BrokerSeamError,
    NeutralOrder,
    OrderType,
    RecordingSink,
    SessionState,
    Side,
    TimeInForce,
)

# The fake is IMPORTED, never copied — see the module docstring on Part C.9.
from test_broker_order import (  # pylint: disable=import-error
    FakeIB,
    fut,
    resolver,
)

LOGGER_NAME = "nix.broker_order.ibkr"

# --- §7.12 answer V2: the imported fake must still carry the surface we drive. -------
# Derived from what these traversals actually call, not a snapshot inventory: adding a
# driver below without adding it here is the only way to widen this, and forgetting to
# is caught by an AttributeError at the call site rather than by a silent no-op.
_FIDELITY = (
    "connectAsync",
    "disconnect",
    "placeOrder",
    "cancelOrder",
    "reqPositionsAsync",
    "push_status",
    "push_exec",
    "push_error",
    "push_position",
    "position_row",
    "reqpos_calls",
    "next_order_id",
    "placed",
    "cancelled",
)
_MISSING = [name for name in _FIDELITY if not hasattr(FakeIB(), name)]
if _MISSING:  # import-time non-vacuity guard, not a test — must fail collection
    raise RuntimeError(
        f"imported FakeIB no longer carries {_MISSING} — these traversals would drive a "
        "fake that cannot represent the vendor surface they are written about"
    )


# ---------------------------------------------------------------------------
# THE ORDERING OBSERVABLE
#
# RecordingSink.sequence records event NAMES only. That is sufficient for the ARC 015
# §2c ack-race proof, which drives exactly ONE order at a time — but "the ack preceded
# the fill FOR THIS ORDER" is a per-identity question, and with two orders in flight a
# name-only log cannot express it. Extending the recorder (Part C.9) rather than
# replacing it: `ordered` sits alongside `sequence`, every existing index keeps meaning
# what it meant, and `RecordingSink` stays the one sink the adapter is written against.
# ---------------------------------------------------------------------------


@dataclass
class OrderedSink(RecordingSink):
    """RecordingSink plus a CID-TAGGED arrival log across all seven streams."""

    ordered: list[tuple[str, str]] = field(default_factory=list)

    def on_ack(self, client_order_id, status, reason=None, *, reject_category=None):
        super().on_ack(client_order_id, status, reason, reject_category=reject_category)
        self.ordered.append(("on_ack", client_order_id))

    def on_fill(
        self, client_order_id, exec_id, symbol, filled_qty, price, cumulative_qty
    ):
        super().on_fill(
            client_order_id, exec_id, symbol, filled_qty, price, cumulative_qty
        )
        self.ordered.append(("on_fill", client_order_id))

    def on_cancel(self, client_order_id, done_qty):
        super().on_cancel(client_order_id, done_qty)
        self.ordered.append(("on_cancel", client_order_id))

    def on_position(self, symbol, net_qty, avg_price):
        super().on_position(symbol, net_qty, avg_price)
        self.ordered.append(("on_position", symbol))

    def on_session(self, state, reason=None):
        super().on_session(state, reason)
        self.ordered.append(("on_session", state.value))


def ack_before_fill_violations(ordered: list[tuple[str, str]]) -> list[str]:
    """Ids whose FIRST on_fill precedes their FIRST on_ack. Empty == guarantee held.

    §2A on_ack is "accepted/rejected ack, never a fill", and the adapter's own §2c
    synthesis exists so a caller "can never observe a fill or a cancel before the ack".
    Asserted per identity, because that is the identity the guarantee is about.
    """
    first: dict[tuple[str, str], int] = {}
    for i, (event, cid) in enumerate(ordered):
        first.setdefault((event, cid), i)
    bad = []
    for (event, cid), idx in first.items():
        if event != "on_fill":
            continue
        ack = first.get(("on_ack", cid))
        if ack is None or ack > idx:
            bad.append(cid)
    return sorted(bad)


def ack_before_fill_violations_blind(sequence: list[str]) -> list[str]:
    """THE CONTROL'S READING. The only question a name-only log can ask.

    With no identity in the record, the strongest available statement is about the
    stream as a whole: did SOME ack precede SOME fill. Written out rather than described
    so the control can demonstrate the blindness behaviourally instead of asserting it.
    """
    for name in sequence:
        if name == "on_ack":
            return []
        if name == "on_fill":
            return ["<stream>"]
    return []


def nonvac(condition: bool, what: str) -> None:
    """Non-vacuity assertion. Distinct from the behavioural asserts on purpose.

    debug.md §7.3: prove the instrument's scope contains its subject BEFORE proving
    anything else. A failure here means the traversal did not reach the state it claims
    to be reporting on, which is CANNOT MEASURE — not a finding about the adapter.
    """
    assert condition, (
        f"NON-VACUITY FAILED (traversal never reached its subject): {what}"
    )


def new_ad(sink: OrderedSink | None = None, ib: FakeIB | None = None):
    """The ONLY construction path — §7.12 answer V4.

    Returns the very objects it injected, so an assertion can never be reading a sink
    the adapter does not write to (the ARC 016 instance of the standing question).
    """
    sink = sink or OrderedSink()
    ib = ib or FakeIB()
    ad = IBKRBrokerOrder(sink, ib=ib, contract_resolver=resolver, client_id=905)
    assert ad._sink is sink and ad._ib is ib
    return ad, ib, sink


def mkt(cid: str, symbol: str = "MESU6", side: Side = Side.BUY, qty: int = 1):
    return NeutralOrder(cid, symbol, side, qty, OrderType.MARKET, TimeInForce.DAY)


class GatedIB(FakeIB):
    """FakeIB whose reqPositionsAsync BLOCKS on an explicit Event.

    Deterministic interleaving, not sleeps and hope (ARC 019 §5/B2). `entered` fires the
    instant the venue call is reached — which is what lets a traversal prove it is INSIDE
    the window rather than assuming it (§7.12 answer V3) — and `release` is what the
    traversal sets to let the venue answer. `snapshots` lets successive calls return
    DIFFERENT position sets, so an overlap can be told apart from a repeat.
    """

    def __init__(self, inner: FakeIB):
        self.__dict__.update(inner.__dict__)  # pylint: disable=super-init-not-called
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.snapshots: list[list] = []
        self.completions: list[int] = []

    async def reqPositionsAsync(self):
        self.reqpos_calls += 1
        call = self.reqpos_calls
        self.entered.set()
        await self.release.wait()
        self.completions.append(call)
        if self.snapshots:
            return self.snapshots.pop(0)
        return self.positions_to_return


async def spin(times: int = 4) -> None:
    """Let the loop dispatch ready callbacks. No wall-clock dependency, so no timing
    window to go stale (debug.md failure mode #6)."""
    for _ in range(times):
        await asyncio.sleep(0)


# ===========================================================================
# THE CONTROL — debug.md §7.1, and the ARC 018 Hollow pattern: asserted
# STRUCTURALLY and BEHAVIOURALLY, so it cannot pass for a shape reason.
# ===========================================================================


def test_control_cid_blind_ordering_is_blind() -> None:
    """CONTROL for §7.12 answer V5: the cid-blind observable misses a real violation.

    PRECONDITIONS: one synthetic arrival stream, two orders. Order `a` is well-behaved
      (its ack precedes its fill). Order `b` is the defect: its fill precedes its ack.
    EXPECTED: the cid-tagged reading NAMES `b`; the cid-blind reading, which is the
      shape `RecordingSink.sequence` provides, reports nothing.
    OBSERVABLE: the two checkers' return values over the same stream.

    WHY A CONTROL AND NOT A NOTE. If the blind reading could see this, every ordering
    assertion below could be made from `sequence` and this suite's extra observable
    would be measuring nothing. The control is the evidence that it is not.
    """
    ordered = [
        ("on_ack", "a"),
        ("on_fill", "a"),
        ("on_fill", "b"),  # <- the planted violation
        ("on_ack", "b"),
    ]
    blind = [event for event, _ in ordered]

    # STRUCTURAL: the blind record carries no identity at all. Not a stylistic point —
    # it is why the behavioural half below is possible.
    assert all(isinstance(x, str) for x in blind)
    assert not any(cid in blind for cid in ("a", "b"))

    # BEHAVIOURAL: same stream, two verdicts.
    assert ack_before_fill_violations(ordered) == ["b"]
    assert ack_before_fill_violations_blind(blind) == [], (
        "the blind reading CAUGHT the violation — the control has stopped controlling "
        "and every ordering claim in this file would need re-deriving"
    )


# ===========================================================================
# T1 — flatten() twice. The protective path against itself.
# ===========================================================================


@pytest.mark.asyncio
async def test_t1_flatten_twice_inside_the_window_emits_once() -> None:
    """SEQUENCE: two concurrently-scheduled `flatten()` calls over one mirrored position.

    PRECONDITIONS: session up, mirror holds MESU6 +2 from a positionEvent.
    OBSERVABLE: `ib.placed`, a per-fan-out sample of `ad._mirror` taken from an
      instrumented contract resolver, and the adapter's flatten ATTEMPT RECORD.

    T3-04 — RESOLVED IN ARC 020 (A6) BY OPERATOR RULING. This traversal previously
    reported the spec gap: two protective flattens over one `+2` mirror emitted `−4` of
    market orders, because `place_order` does not decrement the mirror and only a fill
    does. §2A's `flatten` bullet defines the verb and is silent on repeat invocation, so
    ARC 019 recorded the finding and deliberately did not invent the answer. The ruling
    landed in ARC 020 and §4 "Exits (dual authority)" is the section named:

      A protective `flatten` is idempotent with respect to IN-FLIGHT DECLARED INTENT. A
      second invocation inside the declared window emits NO ADDITIONAL ORDERS and records
      the suppressed attempt. The window is bounded; on expiry the intent is discarded and
      a later `flatten` emits normally. The adapter NEVER auto-refires on expiry.

    So the assertion inverts, in the same motion as the fix, exactly as this file's rule
    requires. What is asserted now:
      - ONE set of orders from two invocations inside the window, sized at the full held
        quantity — a relation derived from the inputs, never a literal (§7.4);
      - exactly ONE suppression recorded, naming the intent it was suppressed by;
      - and the atomicity property that made the old finding reachable is UNCHANGED and
        still asserted: `flatten()` has no await, so both calls read the same `+2` mirror.
        That is what makes suppression necessary rather than incidental — if the second
        call had seen a decremented mirror it would have emitted nothing anyway and this
        traversal would prove nothing about the window.
    """
    ad, ib, sink = new_ad()
    await ad.connect()

    seen_at_fanout: list[int] = []

    def instrumented(symbol: str):
        pos = ad._mirror.get(symbol)
        seen_at_fanout.append(pos.net_qty if pos else 0)
        return fut(symbol)

    ad._resolve_contract = instrumented
    ib.push_position("MESU6", 2, 7773.50)
    nonvac(ad._mirror["MESU6"].net_qty == 2, "mirror never received the position")

    t_a = asyncio.create_task(_call_flatten(ad))
    t_b = asyncio.create_task(_call_flatten(ad))
    await asyncio.gather(t_a, t_b)

    # NON-VACUITY, and it is the SAME guard as before the ruling: the second call really
    # did read an undecremented +2 mirror. A suppression asserted over a call that would
    # have emitted nothing regardless measures nothing.
    nonvac(len(seen_at_fanout) == 1, f"fan-out ran {len(seen_at_fanout)} times, not 1")
    nonvac(
        ad._mirror["MESU6"].net_qty == 2,
        "the mirror was decremented by the send, so suppression was not what stopped the "
        "second emission",
    )
    attempts = ad.flatten_attempts()
    nonvac(
        len(attempts) == 2, f"both flatten calls did not record an attempt: {attempts}"
    )

    # THE RULING: one set of orders from two invocations.
    flats = [o for _c, o, _t in ib.placed]
    held = 2
    assert len(flats) == 1
    assert sum(int(o.totalQuantity) for o in flats) == held
    assert all(o.action == "SELL" for o in flats)

    # ...and the suppression is RECORDED, not merely absent. A protective action that was
    # requested and deliberately not sent is a fact the consumer needs (D1.28).
    first, second = attempts
    assert len(first.intents) == 1 and not first.suppressed
    assert not second.intents and len(second.suppressed) == 1
    sup = second.suppressed[0]
    assert sup.symbol == "MESU6"
    assert sup.prior_client_order_id == first.intents[0].client_order_id
    assert sup.prior_attempt_seq == first.seq
    assert sup.age_ms < sup.window_ms

    # Distinct ids: the guarantee the adapter has always had across repeats.
    ids = [cid for cid, _s, _r, _rc in sink.acks] or list(ad._neutral)
    assert len(set(ids)) == len(ids)


@pytest.mark.asyncio
async def test_t1b_flatten_outside_the_window_emits_again() -> None:
    """The OTHER half of the ruling, and the one that stops idempotency becoming a refusal
    to protect.

    PRECONDITIONS: session up, mirror holds MESU6 +2, one flatten already emitted.
    OBSERVABLE: `ib.placed` across the window boundary.
    EXPECTED: "The window is bounded; on expiry the intent is discarded and a subsequent
      `flatten` emits normally. The adapter never auto-refires on expiry."

    WHY BOTH HALVES ARE REQUIRED. Permanent idempotency was REJECTED in the ruling because
    D1.22 shows a flatten can return normally and never reach the venue — an adapter that
    refused to re-flatten because it "already did" would refuse to protect. So a test that
    only proved suppression would be proving the wrong half of the property.

    THE CLOCK IS MOVED, NOT WAITED ON (debug.md failure mode #6: a test whose timing window
    stops biting). The recorded intent's monotonic timestamp is aged past the window
    directly, so this traversal has no wall-clock dependency and cannot go flaky or go
    stale if the configured window changes.
    """
    ad, ib, _sink = new_ad()
    await ad.connect()
    ib.push_position("MESU6", 2, 7773.50)

    ad.flatten("MESU6")
    nonvac(len(ib.placed) == 1, f"the first flatten did not emit: {ib.placed}")
    cid, ts, seq = ad._flatten_intent["MESU6"]

    # Inside the window: suppressed. Asserted first, so "emits again" below is a
    # transition rather than a state that was always true.
    ad.flatten("MESU6")
    nonvac(len(ib.placed) == 1, "the in-window repeat emitted after all")

    # Age the intent past the window. Derived from the CONFIGURED window, never a literal.
    ad._flatten_intent["MESU6"] = (
        cid,
        ts - (ad._cfg.flatten_idempotency_window_ms / 1000.0) - 0.001,
        seq,
    )
    ad.flatten("MESU6")

    assert len(ib.placed) == 2, (
        f"an EXPIRED intent still suppressed the protective path: {ib.placed}"
    )
    # And nothing fired by itself while the intent sat there expiring.
    attempts = ad.flatten_attempts()
    assert len(attempts) == 3, f"attempts recorded: {[a.seq for a in attempts]}"
    assert [len(a.intents) for a in attempts] == [1, 0, 1]
    assert [len(a.suppressed) for a in attempts] == [0, 1, 0]


@pytest.mark.asyncio
async def test_t1c_flatten_on_an_unheld_symbol_is_observable() -> None:
    """D1.28(b): "already flat" and "the mirror has lost this position" were the same
    SILENCE. They are still the same fact — the adapter genuinely cannot tell them apart —
    but the fact is now written down.

    PRECONDITIONS: session up, empty mirror.
    OBSERVABLE: the attempt record, and `_mirror_stale` captured on it.
    EXPECTED: an observable no-op, not silence. Deliberately NOT an exception: §4's
      flatten-on-uncertainty "may hit nothing OR close a real position", so a protective
      flatten finding nothing is a designed outcome, and raising would make the safe case
      look like a fault. debug.md failure mode #11 asks for an OBSERVABLE, not a throw.
    """
    ad, ib, _sink = new_ad()
    await ad.connect()
    nonvac(
        ad._mirror == {}, "the mirror was not empty — this is not the case under test"
    )

    ad.flatten("MESU6")
    assert not ib.placed

    att = ad.last_flatten_attempt()
    assert att is not None, "a protective flatten produced NO record at all"
    assert att.requested_symbol == "MESU6"
    assert att.no_position == ("MESU6",)
    assert att.is_silent_no_op is True
    assert att.mirror_stale is False  # which of the two worlds — readable, not inferred

    # NON-VACUITY: the same observable can express the OTHER verdict, so `is_silent_no_op`
    # is not simply always True.
    ib.push_position("MESU6", 1, 7773.50)
    ad.flatten("MESU6")
    att2 = ad.last_flatten_attempt()
    assert att2 is not None and att2.is_silent_no_op is False
    assert att2.no_position == () and len(att2.intents) == 1


async def _call_flatten(ad) -> None:
    ad.flatten()


# ===========================================================================
# T2 — flatten() while a fill for the same symbol is arriving.
# ===========================================================================


@pytest.mark.asyncio
async def test_t2_flatten_against_an_arriving_fill() -> None:
    """SEQUENCE: a fill for MESU6 is scheduled to land while `flatten()` runs.

    PRECONDITIONS: session up, mirror holds MESU6 +1, a working order `t2-buy` whose
      fill is queued as a task.
    OBSERVABLE: mirror samples taken from inside flatten's fan-out; the mirror after.

    WHAT IS DETERMINED, and asserted: on a single asyncio loop the fill CANNOT interleave
    inside `flatten()` — flatten has no await point, so the queued fill task stays pending
    for the whole of it. The assertion is ATOMICITY, and the non-vacuity half is that the
    racer was genuinely scheduled and genuinely still pending when flatten returned. That
    is the difference between "the race is impossible here" and "the race was never
    attempted", which are indistinguishable from the end state alone (§7.12 answer V1).

    FINDING T3-06 — WORKING AS INTENDED BUT SURPRISING. flatten() sizes from a SNAPSHOT
    and never re-reads. A fill landing one microsecond after the fan-out leaves the
    protective order under-sized against reality, with no re-check anywhere: after the
    sequence below the mirror is NOT flat, and nothing reports that the protective action
    failed to achieve its purpose. §4's indeterminate path does say the Limiter
    "reconciles against broker truth afterward and publishes whichever is real", so the
    architecture recovers — but that reconciliation is the CONSUMER's, and this adapter
    gives it no signal that a reconcile is owed. Disposition: debt row naming ARC 020,
    consumer-side, alongside D1.20's consumer obligation.

    IF A THREAD IS EVER ADDED to this module the atomicity assertion below inverts and
    becomes the defect report. That is why it is asserted rather than assumed.
    """
    ad, ib, sink = new_ad()
    await ad.connect()
    ib.push_position("MESU6", 1, 7773.50)
    ad.place_order(mkt("t2-buy", qty=1))
    trade = ib.placed[-1][2]

    samples: list[int] = []

    def instrumented(symbol: str):
        pos = ad._mirror.get(symbol)
        samples.append(pos.net_qty if pos else 0)
        return fut(symbol)

    ad._resolve_contract = instrumented

    fill_ran = {"value": False}

    async def deliver_fill() -> None:
        fill_ran["value"] = True
        ib.push_exec(trade, "t2-e1", 1, 7774.00, 1, side="BOT")

    racer = asyncio.create_task(deliver_fill())
    ad.flatten()

    # NON-VACUITY: the racer existed and had NOT run. Without this the atomicity claim
    # is unfalsifiable — a task that was never created also never interleaves.
    nonvac(
        not racer.done(), "the racing fill task had already completed before flatten"
    )
    nonvac(
        not fill_ran["value"],
        "the fill ran DURING flatten — atomicity assumption is wrong",
    )
    nonvac(
        samples == [1], f"flatten fan-out did not run exactly once over +1: {samples}"
    )

    await racer
    assert fill_ran["value"]

    # The finding, stated as an observable: the protective order was sized at 1 while the
    # true exposure became 2, and the mirror is not flat.
    flat_order = ib.placed[-1][1]
    assert int(flat_order.totalQuantity) == 1
    assert flat_order.action == "SELL"
    assert ad._mirror["MESU6"].net_qty == 2
    # ...and nothing on the sink says the protective action is now insufficient.
    assert not any(s[0] is SessionState.UP_DATA_LOSS for s in sink.sessions), (
        "a signal appeared that this traversal was written to report the ABSENCE of"
    )


# ===========================================================================
# T3 — cancel_order() on an order that filled microseconds earlier.
# ===========================================================================


@pytest.mark.asyncio
async def test_t3_cancel_after_fill_reaches_the_wire(caplog) -> None:
    """SEQUENCE: fill an order to completion, then cancel it — ARC 015's collapsed
    transition, taken from the cancel side.

    PRECONDITIONS: session up, `t3-buy` filled 1/1 with a terminal `Filled` status.
    OBSERVABLE: `ib.cancelled`; the sink's ack/cancel streams; the cid-tagged order log.

    WHAT IS DETERMINED, and asserted: the one-ack gate holds. The venue's
    "order to cancel is not found" rejection arrives on errorEvent carrying the order's
    id, and `_ack_once` refuses it because the fill already synthesised an ACCEPTED. So a
    filled order can never be reported REJECTED by a late cancel error. That is the
    §2c guarantee under a sequence §2c was not written for, and it holds.

    FINDING T3-07 — WORKING AS INTENDED BUT SURPRISING. `cancel_order` on a terminal
    order does not raise, returns nothing, and puts a cancel on the wire regardless:
    `_orders` is never pruned on a terminal transition, so every order this adapter has
    ever placed stays cancellable forever. §4 "Partial fill (v1.3, locked)" anticipates
    the race one way round — "if the cancel loses the race and the remainder fills,
    position state reflects cumulative reality" — and is silent on the futile cancel.
    Low harm on its own; it is the ENABLER for T3-01 (see test_t10), which is not low
    harm, and the two share one repair.
    """
    caplog.set_level(logging.ERROR, logger=LOGGER_NAME)
    ad, ib, sink = new_ad()
    await ad.connect()
    ad.place_order(mkt("t3-buy", qty=1))
    trade = ib.placed[-1][2]

    ib.push_exec(trade, "t3-e1", 1, 7773.50, 1, side="BOT")
    ib.push_status(trade, "Filled", filled=1)

    # NON-VACUITY: the order really is terminal, and the ack really did precede the fill,
    # before anything is concluded about the cancel that follows.
    nonvac(len(sink.fills) == 1, f"the fill never landed: {sink.fills}")
    nonvac(
        ack_before_fill_violations(sink.ordered) == [],
        "the pre-condition guarantee (ack before fill) was already broken",
    )
    nonvac(ad.query_order_status("t3-buy").terminal, "order is not terminal")

    cancels_before = len(ib.cancelled)
    ad.cancel_order("t3-buy")  # no raise, no signal
    assert len(ib.cancelled) == cancels_before + 1

    # The venue answers "too late". IBKR 10147 = order to cancel not found.
    ib.push_error(
        trade.order.orderId, 10147, "OrderId 1 that needs to be cancelled is not found"
    )

    assert len(sink.acks) == 1, (
        f"a late cancel error produced a second ack: {sink.acks}"
    )
    assert sink.acks[0][1].value == "accepted"
    assert not sink.cancels, f"a filled order reported on_cancel: {sink.cancels}"
    assert ack_before_fill_violations(sink.ordered) == []


# ===========================================================================
# T4 — place_order() immediately followed by disconnect(). Teardown in flight.
# ===========================================================================


@pytest.mark.asyncio
async def test_t4_fill_after_disconnect_is_dropped_and_misattributed(caplog) -> None:
    """SEQUENCE: place an order, tear the session down, then the venue reports its fill.

    PRECONDITIONS: session up, `t4-buy` placed and mapped in `_from_ib`.
    OBSERVABLE: the sink's fill stream; the adapter's ERROR log records.

    WHAT IS DETERMINED, and asserted: the fill is refused. `disconnect()` shuts the
    startup gate deliberately — "between disconnect and the next connect, any order-path
    event still in flight belongs to a session that no longer exists" — and the refusal is
    LOUD rather than silent, which is right (debug.md §7.9, failure mode #11).

    FINDING T3-03 — CODE DEFECT (diagnostic, not behavioural). The loud message names a
    cause that cannot be true here. `_log_gated_drop` says the event was refused because
    "an order was placed concurrently with connect(), violating §4 cold-start ordering" —
    but this drop happens on the DISCONNECT side of the session, with no connect() in
    flight at all. The gate flag is shared by two distinct windows and the log assumes it
    is only ever in one of them. A future debugger reading this line is sent to §4's
    cold-start ordering to look for a violation that did not occur. Repair is one branch
    on `_connected`; it is adapter-internal and does not need a consumer.
    Disposition: trivial, fixable in Phase 4. **REPAIRED, ARC 019 Phase 4** — the two
    windows now branch on `_connected` and the disconnect side names its own cause and
    points at `query_order_status` (§4:241, never auto-resend). The assertion below was
    inverted in the same motion, exactly as this file's strict-xfail rule requires: a
    marker left standing over a repaired defect is a permanently-green measurement of
    nothing.

    NOT ASSERTED, because the spec does not determine it: whether a fill arriving after a
    requested disconnect SHOULD be published. §2A defines `disconnect()` as "tear down the
    venue session" and defines no post-teardown event policy; §14's "Every uncertainty
    resolves toward flat" argues for surfacing it, §4's "Restart = flat, always" and the
    cold-start re-query argue the consumer recovers anyway. THE SECTION THAT WOULD HAVE TO
    SAY: §2A's `connect() / disconnect()` bullet, or §4 "Boot / known-state discipline".
    """
    caplog.set_level(logging.ERROR, logger=LOGGER_NAME)
    ad, ib, sink = new_ad()
    await ad.connect()
    ad.place_order(mkt("t4-buy", qty=1))
    trade = ib.placed[-1][2]
    ib_id = trade.order.orderId

    nonvac(ad._from_ib.get(ib_id) == "t4-buy", "the id map was never populated")
    nonvac(ad._startup_complete is True, "the gate was already shut before disconnect")

    ad.disconnect()
    # NON-VACUITY for the window: shut gate, live id map. Both are required for the loud
    # branch of _log_gated_drop to be the one that runs.
    nonvac(ad._startup_complete is False, "disconnect did not shut the gate")
    # ARC 020 A1: the LIVE registry is cleared at teardown (that clearing is what stops a
    # cancel putting a foreign order's id on the wire), so the loud branch now reads the
    # diagnostics-only copy of the session that just ended. Both halves are asserted —
    # the live map must be EMPTY and the prior map must still NAME the order — because
    # either one alone would leave this traversal unable to tell "cleared" from "moved".
    nonvac(
        ib_id not in ad._from_ib,
        "the live id map survived the teardown — A1's clearing did not happen",
    )
    nonvac(
        ad._prior_from_ib.get(ib_id) == "t4-buy",
        "the prior-session map does not name the order — the loud branch is unreachable "
        "and the drop would be anonymous",
    )

    caplog.clear()
    ib.push_exec(trade, "t4-e1", 1, 7773.50, 1, side="BOT")

    assert not sink.fills, f"the fill crossed the seam after teardown: {sink.fills}"
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert len(errors) == 1, f"the drop was not loud exactly once: {errors}"
    message = errors[0].getMessage()
    assert "t4-buy" in message  # it names the site — that half was always right
    # T3-03 REPAIRED in ARC 019 Phase 4, and this is the invariant the finding's
    # assertion was standing in for: the loud drop must name a cause that CAN be true in
    # the window it fired in. `_connected` is the discriminator — True inside connect(),
    # False after disconnect() — so the connect()-side cause must not appear here.
    assert "concurrently with connect()" not in message, (
        "the drop on the DISCONNECT side is again naming the connect()-side cause; "
        "T3-03 has regressed"
    )
    assert "indeterminate" in message, (
        f"the drop does not point at the §4 outcome that now exists for it: {message}"
    )
    assert "disconnect()" in message, (
        f"the drop does not name the window it actually fired in: {message}"
    )
    assert ad._connected is False


# ===========================================================================
# T5 — disconnect() during an in-flight place_order(). The same, inverted.
# ===========================================================================


@pytest.mark.asyncio
async def test_t5_disconnect_cannot_interleave_inside_place_order() -> None:
    """SEQUENCE: a `disconnect()` is scheduled, then `place_order()` runs.

    PRECONDITIONS: session up, a disconnect queued as a task.
    OBSERVABLE: the queued task's done-state sampled from inside the send path (via the
      instrumented resolver, which runs between `_require_session` and `ib.placeOrder`).

    WHAT IS DETERMINED, and asserted: `place_order` has no await point, so the check-then-
    act between `_require_session("place_order")` and `self._ib.placeOrder(...)` — a
    textbook debug.md Stage-1 race shape — is NOT reachable on one loop. The sample is
    taken at exactly the point a racer would have to land, which is what makes this a
    measurement rather than an argument. Non-vacuity: the racer existed, was pending at
    the sample, and ran afterwards.

    NO FINDING. Recorded because a Tier-3 traversal that only reports defects has not
    established which sequences are safe, and §5.8 says a module is certified because the
    things that would have failed were TRIED.
    """
    ad, ib, _sink = new_ad()
    await ad.connect()

    observed: list[bool] = []

    async def do_disconnect() -> None:
        ad.disconnect()

    racer = asyncio.create_task(do_disconnect())

    def instrumented(symbol: str):
        observed.append(racer.done())
        return fut(symbol)

    ad._resolve_contract = instrumented
    ad.place_order(mkt("t5-buy", qty=1))

    nonvac(observed == [False], f"the send path was not sampled mid-flight: {observed}")
    nonvac(not racer.done(), "the disconnect completed before place_order returned")
    assert ad._connected is True
    assert len(ib.placed) == 1

    await racer
    assert ad._connected is False


@pytest.mark.asyncio
async def test_t5b_order_status_is_stale_across_a_session_boundary() -> None:
    """SEQUENCE: place an order, lose the session, reconnect, ask for its status.

    FINDING T3-02 — REPAIRED IN ARC 020 (A1, D1.24). The `strict=True` xfail that held this
    open is removed in the same motion as the fix, per this file's rule. `_trades` no
    longer survives a session boundary; an order that was NON-TERMINAL when the session
    ended is TOMBSTONED, and `query_order_status` answers `indeterminate` — §4's own third
    outcome, which this adapter previously could not reach.

    PRECONDITIONS: `t5b-buy` placed in session 1 and left working; disconnect; connect.
    EXPECTED INVARIANT (spec-determined): §4 "Failure resolution" names exactly three
      outcomes for a pending-timeout query — "Resolves confirmed / cancelled /
      **indeterminate**". An order that lived in a session that no longer exists is the
      indeterminate case by construction: this adapter cleared `_to_ib`/`_from_ib` on
      connect precisely because IBKR ids do not survive a session, so it has already
      conceded it cannot map that order to anything at the venue.
    OBSERVABLE: `query_order_status("t5b-buy").state`.
    ACTUAL: `_trades` is not cleared on connect, so the cached `Trade.orderStatus` from
      the dead session is returned verbatim — `state="working"`, `terminal=False`, and no
      staleness marker of any kind. A Limiter polling this to resolve a pending timeout
      is told, forever, that the order is still working. The one branch that CAN report
      uncertainty (`state="unknown"`) is reachable only when the trade is ABSENT, which is
      the case this sequence guarantees will not happen.
    §7.12 for this assertion: it would pass vacuously if the session boundary never
      occurred, so `connect_count` and the cleared id map are asserted first.
    """
    ad, ib, _sink = new_ad()
    await ad.connect()
    ad.place_order(mkt("t5b-buy", qty=1))
    ib.push_status(ib.placed[-1][2], "Submitted")

    nonvac(
        ad.query_order_status("t5b-buy").state == "working", "order never went working"
    )
    ad.disconnect()
    await ad.connect()
    nonvac(ib.connect_count == 2, "the second session was never established")
    nonvac(not ad._from_ib, "the id map survived the session boundary")

    status = ad.query_order_status("t5b-buy")
    assert status.state in ("unknown", "indeterminate"), (
        f"a dead session's order still reports {status.state!r} with terminal="
        f"{status.terminal} — §4 has no fourth outcome for it to be reported as"
    )
    # ARC 020 A1: and it is the SPECIFIC one, not the generic "never heard of it".
    # `unknown` would also be the answer for an id that was never placed, and a Limiter
    # must respond differently to those two — §4 sends a flatten-on-uncertainty for one
    # and may freely mint the id for the other.
    assert status.state == "indeterminate", (
        f"a dead session's IN-FLIGHT order reports {status.state!r}, which is this "
        "adapter's spelling of 'no record at all' — the two most different facts in the "
        "set would share one answer"
    )
    assert status.terminal is False, "nothing was resolved, so nothing is terminal"

    # NON-VACUITY: `indeterminate` is not simply what this verb always says now. An id
    # that was NEVER placed still answers `unknown`, and a live order in this session
    # answers its real state.
    assert ad.query_order_status("t5b-never-placed").state == "unknown"
    ad.place_order(mkt("t5b-live", qty=1))
    ib.push_status(ib.placed[-1][2], "Submitted")
    assert ad.query_order_status("t5b-live").state == "working"

    # And the id is NOT re-mintable while the answer is outstanding: two orders under one
    # id — one possibly live at the venue, one certainly live — is the ambiguity §4's
    # pending-timeout resolution exists to remove.
    with pytest.raises(BrokerSeamError, match="IN FLIGHT"):
        ad.place_order(mkt("t5b-buy", qty=1))
    # ...nor cancellable, which is the D1.24(a) half: the stale vendor id would target
    # whichever order the venue has since assigned it to.
    with pytest.raises(BrokerSeamError, match="has ended"):
        ad.cancel_order("t5b-buy")


# ===========================================================================
# T6 — a caller that abandons midway. asyncio task cancellation.
# ===========================================================================


@pytest.mark.asyncio
async def test_t6_query_positions_cancelled_mid_flight_leaves_the_mirror_intact() -> (
    None
):
    """SEQUENCE: `query_positions()` is cancelled while awaiting the venue.

    PRECONDITIONS: session up, mirror holds MESU6 +1 from an event; the venue call is
      gated so the cancel lands strictly INSIDE the await.
    EXPECTED INVARIANT: the mirror is derived from fills first (§4: "position state
      derives from cumulative fills"), and a read that never completed must not be able to
      change it. Abandoning a read must be a no-op on state.
    OBSERVABLE: `ad._mirror` before and after; `ib.reqpos_calls`; the task's cancelled().

    NO FINDING. `query_positions` writes `self._mirror` only after the await returns, so
    cancellation cannot leave a half-applied snapshot, and `CancelledError` is a
    BaseException so `_rebuild_mirror`'s `except Exception` correctly does not swallow it.
    """
    ad, ib, _sink = new_ad()
    await ad.connect()
    ib.push_position("MESU6", 1, 7773.50)
    before = dict(ad._mirror)

    gated = GatedIB(ib)
    gated.snapshots = [[]]  # the venue would have said FLAT
    # Derived, not literal: connect()'s own rebuild already consumed a call, and the
    # count is inherited with the rest of the fake's state (§7.4 — never anchor to a
    # number that describes the current state of the world).
    calls_before = gated.reqpos_calls
    ad._ib = gated
    task = asyncio.create_task(ad.query_positions())
    await gated.entered.wait()

    # NON-VACUITY: the cancel lands INSIDE the venue await, not before it. Cancelling a
    # task that never reached the await proves nothing about mid-flight abandonment.
    nonvac(gated.reqpos_calls == calls_before + 1, "the venue call was never entered")
    nonvac(not task.done(), "the task finished before it could be cancelled")

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert task.cancelled()
    assert dict(ad._mirror) == before
    assert gated.completions == [], "the gated call completed despite being cancelled"


@pytest.mark.asyncio
async def test_t6b_cancelled_connect_leaves_a_deaf_but_accepting_adapter() -> None:
    """SEQUENCE: `asyncio.wait_for(connect(), t)` times out during the mirror rebuild.

    FINDING T3-01 — REPAIRED IN ARC 020 (A2, D1.23). The `strict=True` xfail is removed in
    the same motion as the fix. `connect()` now wraps the whole establishment in
    `except BaseException` — the class `CancelledError` actually belongs to, which is why
    every `except Exception` in the module missed it — unwinds the session, and RE-RAISES.

    PRECONDITIONS: no session; the venue's position read is gated so the cancel lands
      strictly between `_connected = True` and `_startup_complete = True`.
    EXPECTED INVARIANT: a connect that did not complete must not leave a usable-looking
      adapter. §14 "Every uncertainty resolves toward flat. Known state beats optimal
      state" and §2A invariant 1 (the command set is satisfied or it isn't done) both
      point one way: a half-open session must refuse commands, not accept them into a
      channel whose replies are discarded.
    OBSERVABLE: `_connected`, `_startup_complete`, and — the part that matters — whether a
      subsequent `place_order` succeeds and whether its fill reaches the sink.
    ACTUAL: `connect()` sets `_connected = True`, then awaits `_rebuild_mirror()`, then
      sets `_startup_complete = True`. A cancellation between those two lines propagates
      out of connect() (CancelledError is a BaseException, so `_rebuild_mirror`'s
      `except Exception` does not catch it) and NOTHING unwinds `_connected`. The result
      is the worst combination available: `_require_session` passes, so orders go to the
      venue, while the startup gate is permanently shut, so every orderStatus and every
      execution for those orders is refused. `on_session` was never emitted either, so a
      consumer has been told nothing at all. The order path is live and mute.
    HOW REACHABLE: any caller that bounds connect() with a timeout — which is the ordinary
      way to call a verb the spec describes as "allowed to take as long as the venue
      takes" — plus a slow `reqPositionsAsync`. No coincidence is required.
    RELATIONSHIP TO SUB-AGENT A: A's D1.20 work makes `connect()` honour the rebuild
      verdict. That is a different line and does not close this: the verdict is never
      computed when the await is cancelled.
    §7.12 for this assertion: it would pass vacuously if the cancel landed before the
      window opened, so `_connected`/`_startup_complete`/`reqpos_calls` are all asserted
      at the instant the cancel is issued.
    """
    ad, ib, sink = new_ad()
    gated = GatedIB(ib)
    ad._ib = gated

    task = asyncio.create_task(ad.connect())
    await gated.entered.wait()

    # NON-VACUITY: we are inside the exact window, not before or after it.
    nonvac(ad._connected is True, "_connected was not yet set — cancel lands too early")
    nonvac(
        ad._startup_complete is False,
        "the gate was already open — cancel lands too late",
    )
    nonvac(gated.reqpos_calls == 1, "the rebuild's venue call was never entered")

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert not (ad._connected and not ad._startup_complete), (
        f"abandoned connect left _connected={ad._connected} / "
        f"_startup_complete={ad._startup_complete}: the adapter accepts orders it can "
        f"never report on. sink.sessions={sink.sessions}"
    )
    # THE REFUSAL IS OBSERVABLE TO THE CALLER, which is the half that matters. The old
    # state was not merely wrong — it was silently wrong, and a consumer had no way to ask.
    with pytest.raises(BrokerNotConnected):
        ad.place_order(mkt("t6b-buy", qty=1))
    assert not ib.placed, (
        f"an order reached the venue after an abandoned connect: {ib.placed}"
    )
    # ...and cancellation SEMANTICS survive: the CancelledError was re-raised, not
    # swallowed. `pytest.raises(asyncio.CancelledError)` above is that assertion; a
    # handler that swallowed it would have made this a normal return.
    assert task.cancelled()


@pytest.mark.asyncio
async def test_t6c_cancelled_connect_the_evidence() -> None:
    """The BEHAVIOURAL half of T3-01, now asserting the REPAIRED behaviour.

    WHAT THIS MEASURED BEFORE ARC 020, recorded because the blast radius is the reason the
    repair was not a one-liner: after a cancelled connect the adapter ACCEPTED an order and
    it REACHED THE VENUE (`len(ib.placed) == 1`) while `sink.acks == []`, `sink.fills ==
    []`, `_mirror == {}` and no `on_session` had ever been published. The order path was
    live and mute. debug.md §7.9: "the adapter accepted the order" was a measured PASS of
    the wrong thing.

    WHAT IT ASSERTS NOW: the order never leaves. `_abandon_session` clears `_connected`, so
    `_require_session` refuses, and the refusal is a raised `BrokerNotConnected` rather than
    a silently-discarded send.

    THE FIRST-EVER-CONNECT CASE IS DELIBERATELY THE ONE DRIVEN HERE, because it is where
    the two repairs meet: no `on_session` is published, and that is now CORRECT rather than
    a gap. §2A defines `on_session` as connectivity TRANSITIONS (D1.28(c)); this adapter
    never announced a session, so a DOWN would report a change that did not occur. The
    caller is not left uninformed — the `CancelledError` it receives IS the notification,
    and `place_order` refuses loudly thereafter. `test_t6d` drives the OTHER case, where a
    session did exist and the transition is real.
    """
    ad, ib, sink = new_ad()
    gated = GatedIB(ib)
    ad._ib = gated
    task = asyncio.create_task(ad.connect())
    await gated.entered.wait()
    nonvac(ad._connected is True, "the cancel would land before the window")
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    nonvac(
        ad._connected is False and ad._startup_complete is False,
        f"the session was not unwound: connected={ad._connected} "
        f"gate={ad._startup_complete}",
    )

    ad._ib = ib  # the transport is fine; the adapter must refuse on its own state
    with pytest.raises(BrokerNotConnected):
        ad.place_order(mkt("t6c-buy", qty=1))

    assert not ib.placed, "an order reached the venue after an abandoned connect"
    assert not sink.acks and not sink.fills
    assert ad._mirror == {}
    assert ad._mirror_stale is True, (
        "the rebuild's verdict was never computed, so the mirror behind flatten() is "
        "exactly the 'possibly behind the venue' state that flag names"
    )
    # §2A "connectivity transitions": nothing was ever announced, so nothing is retracted.
    assert not sink.sessions, f"a non-transition DOWN was published: {sink.sessions}"


@pytest.mark.asyncio
async def test_t6d_a_cancelled_RECONNECT_publishes_a_real_DOWN_edge() -> None:
    """The other half of the D1.23 repair: when a session DID exist, the consumer is told.

    PRECONDITIONS: a first session established (UP published), then a reconnect cancelled
      inside the rebuild.
    OBSERVABLE: the session stream, and whether `place_order` is refused afterwards.
    EXPECTED: a DOWN edge, because this one IS a transition — the consumer was told the
      session was up and it is not any more. Contrast `test_t6c`, where nothing had ever
      been announced.

    NON-VACUITY: the UP is asserted BEFORE the cancel, so "a DOWN was published" is an
    UP -> DOWN transition and not a DOWN over a stream that was already down.
    """
    ad, ib, sink = new_ad()
    await ad.connect()
    nonvac(sink.sessions[-1][0] is SessionState.UP, f"no UP published: {sink.sessions}")
    ad.disconnect()
    nonvac(sink.sessions[-1][0] is SessionState.DOWN, "no DOWN on the clean teardown")
    await ad.connect()
    nonvac(sink.sessions[-1][0] is SessionState.UP, "the second session never came up")
    before = len(sink.sessions)

    gated = GatedIB(ib)
    ad._ib = gated
    task = asyncio.create_task(ad.connect())
    await gated.entered.wait()
    nonvac(ad._connected is True, "the cancel lands too early")
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    published = sink.sessions[before:]
    assert [s[0] for s in published] == [SessionState.DOWN], (
        f"a cancelled reconnect over a previously-UP session published {published}"
    )
    assert "abandoned" in (published[0][1] or ""), (
        f"the reason does not say the connect was abandoned: {published[0][1]!r}"
    )
    with pytest.raises(BrokerNotConnected):
        ad.place_order(mkt("t6d-buy", qty=1))


# ===========================================================================
# T7 — flatten() during a reconnect. Protective path over an unrebuilt mirror.
# ===========================================================================


@pytest.mark.asyncio
async def test_t7_flatten_during_reconnect_is_observed_by_the_ownership_gate() -> None:
    """SEQUENCE: a protective `flatten()` is issued while `connect()` awaits the rebuild.

    PRECONDITIONS: a first session established and dropped; the mirror still holds the
      previous session's MESU6 +1; a second `connect()` gated inside `_rebuild_mirror`.
    OBSERVABLE: `ib.placed` (did the protective path fire), and the sink (was anything
      about those orders reported).

    FINDING T3-05 — RESOLVED IN ARC 020 (A4) BY OPERATOR RULING. ARC 019 measured, and this
    traversal asserted, that the protective path DID fire during re-establishment and that
    every ack and fill for the orders it fired was refused by the still-shut startup gate.
    §14's "the exit/protective path has zero wire/delivery dependency" was honoured in the
    sense that nothing blocked, and violated in the sense that mattered: the outcome of the
    protective action was unobservable. The spec did not choose, so ARC 019 recorded the gap
    and named §4 "Boot / known-state discipline" as the section that would have to say.

    THE RULING, ratified in ARC 020: the startup admission gate discriminates by ORDER
    OWNERSHIP, not by elapsed time. Events whose id is in the CURRENT session's registry are
    admitted regardless of startup state; all others are refused. So this traversal's
    assertions invert, in the same motion as the fix.

    WHY THIS DOES NOT REOPEN THE ARC 017 PHANTOM FILL, asserted below rather than argued:
    the registry is cleared BEFORE `connectAsync`, and the venue's startup replay is
    dispatched from INSIDE `connectAsync`. So no replayed id can be in the registry during
    this window, and every id that IS in it was minted by a `place_order` in this session.
    The A1 dependency is not optional and is asserted here: a PRE-BOUNDARY id must not be
    admitted, or the gate has become one that can be fooled.
    """
    ad, ib, sink = new_ad()
    await ad.connect()
    ib.push_position("MESU6", 1, 7773.50)
    ad.place_order(mkt("t7-stale", qty=1))
    stale_ib_id = ad._to_ib["t7-stale"]
    stale_trade = ib.placed[-1][2]
    ad.disconnect()
    nonvac(ad._mirror.get("MESU6") is not None, "the mirror did not survive the drop")

    gated = GatedIB(ib)
    ad._ib = gated
    reconnect = asyncio.create_task(ad.connect())
    await gated.entered.wait()

    # NON-VACUITY: inside the reconnect window — session usable, gate shut, mirror not
    # yet rebuilt. All three are required for this to be the sequence being reported.
    nonvac(
        ad._connected is True, "the session is not usable — flatten would just raise"
    )
    nonvac(ad._startup_complete is False, "the gate is open — this is not the window")
    nonvac(gated.completions == [], "the rebuild already landed")

    # ---- THE A1 DEPENDENCY, asserted BEFORE the admission it makes safe --------------
    # A pre-boundary vendor id must not be in the registry. If it were, this would no
    # longer be an ownership gate — it would be a gate that launders a foreign order into
    # ownership, which is exactly what the ruling says it is sound only in the absence of.
    nonvac(
        stale_ib_id not in ad._from_ib,
        f"a PRE-BOUNDARY vendor id {stale_ib_id} is in the live registry — the ownership "
        "gate can be fooled and A4 is unsound",
    )
    ib.push_exec(stale_trade, "t7-stale-e", 1, 7773.00, 1, side="SLD")
    assert not sink.fills, (
        f"an event carrying a PRE-BOUNDARY id was admitted during the startup window: "
        f"{sink.fills}"
    )

    # ---- and now the admission the ruling exists for ---------------------------------
    placed_before = len(ib.placed)
    ad._ib = ib  # orders go to the real fake; the rebuild stays gated
    ad.flatten()
    fired = ib.placed[placed_before:]
    assert len(fired) == 1 and fired[0][1].action == "SELL"

    trade = fired[0][2]
    nonvac(
        trade.order.orderId in ad._from_ib,
        "the protective order was not registered — nothing would be owned to admit",
    )
    ib.push_status(trade, "Submitted")
    ib.push_exec(trade, "t7-e1", 1, 7773.00, 1, side="SLD")
    assert sink.acks, (
        "the protective exit's ACK was refused during re-establishment — the outcome of a "
        "protective action is unobservable, which is what the ruling exists to fix"
    )
    assert sink.fills, "the protective exit's FILL was refused during re-establishment"
    owned_cid = ad._from_ib[trade.order.orderId]
    assert [c for c, *_ in sink.acks] == [owned_cid]
    assert [f[0] for f in sink.fills] == [owned_cid]

    ad._ib = gated
    gated.release.set()
    await reconnect
    assert ad._startup_complete is True


# ===========================================================================
# T8 — identity reuse.
# ===========================================================================


@pytest.mark.asyncio
async def test_t8_client_order_id_is_never_released() -> None:
    """SEQUENCE: complete an order, then reuse its id — first in the same session, then
    across a reconnect.

    PRECONDITIONS: `t8-buy` placed and filled 1/1 to a terminal state.
    OBSERVABLE: the exception from the second and third `place_order`; the sizes of the
      adapter's per-order maps across the session boundary.

    WHAT IS DETERMINED, and asserted: the duplicate guard refuses, in both cases. Refusing
    is the safe direction — §2A's `place_order` returns "an accepted/rejected ack, never a
    fill", and two live orders under one id would make the ack stream ambiguous, which is
    the failure the module docstring's no-retry policy exists to prevent.

    FINDING T3-08 — NARROWED IN ARC 020 (A1). The asymmetry was: `connect()` cleared
    `_to_ib`/`_from_ib`/`_acked`/`_cancelled` because "session boundary invalidates every
    IBKR-side id" and left `_neutral`/`_orders`/`_trades`/`_seen_execs` standing, so the
    NEUTRAL id space was permanently consumed for the life of the process while the VENDOR
    id space reset. A Limiter minting deterministic ids (strategy+sequence) was blocked
    after a Gateway restart on an id that meant nothing at the venue.

    WHAT IS TRUE NOW, and it is a partition rather than a reversal:
      - an id whose order reached a TERMINAL state is RELEASED at the boundary. Its outcome
        is known and recorded and §4's pending-timeout query has nothing left to resolve, so
        holding the id costs a Limiter its deterministic id space for nothing. Re-mintable.
      - an id whose order was IN FLIGHT at the boundary is NOT released. Its venue-side fate
        is unresolved; two orders under one id — one possibly live at the venue, one
        certainly live — is the ambiguity §4's pending-timeout resolution exists to remove.
        Refused, with a message that says WHICH refusal it is (`test_t5b` drives that half).
    WITHIN a session nothing changed: an id is single-use, and the duplicate guard is the
    same one.
    """
    ad, ib, sink = new_ad()
    await ad.connect()
    ad.place_order(mkt("t8-buy", qty=1))
    trade = ib.placed[-1][2]
    ib.push_exec(trade, "t8-e1", 1, 7773.50, 1, side="BOT")
    ib.push_status(trade, "Filled", filled=1)

    nonvac(len(sink.fills) == 1, "the order never completed")
    nonvac(ad.query_order_status("t8-buy").terminal, "the order is not terminal")

    # WITHIN the session: unchanged. Still single-use.
    with pytest.raises(BrokerSeamError, match="duplicate client_order_id"):
        ad.place_order(mkt("t8-buy", qty=1))

    ad.disconnect()
    await ad.connect()
    nonvac(ib.connect_count == 2, "no second session")
    nonvac(not ad._from_ib, "the vendor id map survived the boundary")

    # ACROSS the boundary: a TERMINAL order's state is gone, in every map, and its neutral
    # id is re-mintable. Asserted as a relation over the maps, not a count.
    assert not any(
        "t8-buy" in m for m in (ad._neutral, ad._orders, ad._trades, ad._to_ib)
    ), (
        "terminal per-order state survived a session boundary: "
        f"neutral={'t8-buy' in ad._neutral} orders={'t8-buy' in ad._orders} "
        f"trades={'t8-buy' in ad._trades} to_ib={'t8-buy' in ad._to_ib}"
    )
    assert "t8-buy" not in ad._tombstones, (
        "a TERMINAL order was tombstoned — the tombstone is for orders whose fate is "
        "unresolved, and this one's is not"
    )
    ad.place_order(mkt("t8-buy", qty=1))
    assert ad._to_ib.get("t8-buy") is not None, (
        "a terminal order's neutral id was still blocked after a session boundary"
    )


# ===========================================================================
# T9 — two place_order() calls interleaved with a fill for the first.
# ===========================================================================


@pytest.mark.asyncio
async def test_t9_ack_before_fill_holds_per_order_under_interleaving() -> None:
    """SEQUENCE: place A, place B, fill A, ack B, fill B — the streams interleaved.

    PRECONDITIONS: session up, two orders in flight simultaneously.
    EXPECTED INVARIANT: `_ensure_acked` promises that a caller "can never observe a fill
      or a cancel before the ack" — a PER-IDENTITY guarantee. Asserted per identity.
    OBSERVABLE: the cid-tagged arrival log.

    NON-VACUITY, and the reason this test exists at all: the sequence must actually
    INTERLEAVE. A run in which A completes entirely before B begins would satisfy every
    assertion here while demonstrating nothing about interleaving, and would be
    indistinguishable from a real interleave in `RecordingSink.sequence`. So the traversal
    asserts that at least one B event sits strictly between two A events.

    FINDING T3-09 — INSTRUMENT FIDELITY (debug.md §5.7, the instrument audit Tier 3
    requires). `RecordingSink.sequence` records event NAMES only. Its docstring says it
    exists because "the per-stream lists above cannot express 'the ack preceded the fill'
    — that is a cross-stream ordering property" — but the log it provides can express that
    only for a stream containing exactly ONE order, which is the only shape
    `_section_ack_race` drives. With two orders in flight the ordering guarantee is not
    expressible from it, and the adapter could emit B's fill before B's ack with the
    existing suite still green. This suite's `OrderedSink` is the extension; the control
    `test_control_cid_blind_ordering_is_blind` is the proof that the extension is
    load-bearing rather than decorative. Disposition: trivial — `sequence` gains the id,
    appended so no existing index changes. Sub-agent A owns `RecordingSink`'s file.
    """
    ad, ib, sink = new_ad()
    await ad.connect()
    ad.place_order(mkt("t9-a", qty=2))  # partially fillable, so A outlives B
    trade_a = ib.placed[-1][2]
    ad.place_order(mkt("t9-b", symbol="MNQU6", qty=1))
    trade_b = ib.placed[-1][2]

    nonvac(len(ib.placed) == 2, "both orders did not reach the venue")
    nonvac(trade_a.order.orderId != trade_b.order.orderId, "the venue reused an id")

    # The interleave, driven deliberately: B's whole lifecycle sits INSIDE A's, and A's
    # second fill lands after B is done. Both streams are live at once, which is the only
    # arrangement in which a per-identity ordering guarantee can actually be tested.
    ib.push_status(trade_a, "Submitted")  # A acked
    ib.push_status(trade_b, "Submitted")  # B acked
    ib.push_exec(trade_a, "t9-ea1", 1, 7773.50, 1, side="BOT")  # A partial
    ib.push_exec(trade_b, "t9-eb1", 1, 21000.25, 1, side="BOT")  # B filled
    ib.push_exec(trade_a, "t9-ea2", 1, 7773.75, 2, side="BOT")  # A completes

    order = sink.ordered
    a_idx = [i for i, (_e, c) in enumerate(order) if c == "t9-a"]
    b_idx = [i for i, (_e, c) in enumerate(order) if c == "t9-b"]
    nonvac(len(a_idx) >= 2 and len(b_idx) >= 2, f"both orders did not emit: {order}")
    nonvac(
        any(min(a_idx) < j < max(a_idx) for j in b_idx)
        or any(min(b_idx) < i < max(b_idx) for i in a_idx),
        f"the two orders' event streams never interleaved: {order}",
    )

    assert ack_before_fill_violations(order) == []
    # And the finding, demonstrated on this very stream: the blind reading cannot make
    # the same statement — it stops at the first ack in the whole stream.
    assert ack_before_fill_violations_blind(sink.sequence) == []
    assert not any(cid in sink.sequence for cid in ("t9-a", "t9-b"))


# ===========================================================================
# T10 — cancel across a session boundary. ADDED SEQUENCE.
# ===========================================================================


@pytest.mark.asyncio
async def test_t10_cancel_across_a_session_boundary_targets_a_foreign_order() -> None:
    """SEQUENCE (ADDED — why: the adapter's own comments make this reachable and say so).

    `connect()` clears `_to_ib`/`_from_ib` with the reason written at the site: "IBKR
    orderIds are ints from a per-session sequence that RESETS across Gateway restarts ...
    this map must never be assumed to survive a session." `_orders` is not cleared — and
    `_orders` holds the ib `Order` OBJECT, which carries `orderId` as an attribute.
    `cancel_order` sends that object. So the one piece of state that actually reaches the
    wire is the piece the session-boundary reasoning did not cover. Reaching it needs no
    race at all: place, Gateway's 03:00 restart, place, cancel the first.

    PRECONDITIONS: `t10-old` placed in session 1; session dropped and re-established
      (FakeIB resets `next_order_id`, as the Gateway does); `t10-new` placed in session 2.
    EXPECTED INVARIANT: a cancel must never carry an identifier that resolves to an order
      the caller did not name. §2A `cancel_order(client_order_id)` is defined on the
      NEUTRAL id, and §2A invariant 2 makes the neutral-to-venue mapping the adapter's
      sole responsibility; a mapping the adapter has itself declared invalid is not a
      mapping it may keep using.
    OBSERVABLE: the `orderId` on the object handed to `ib.cancelOrder`, compared against
      the live mapping for the NEW order. Derived from the run, not written down.
    §7.12 for this assertion: it would pass vacuously if the fake did not reset its id
      sequence across connect — then the two orders would never collide. The reset is
      asserted before the comparison.

    FINDING T3-01b — REPAIRED IN ARC 020 (A1, D1.24(a)). The `strict=True` xfail is removed
    in the same motion as the fix. `_orders` is now released at every session boundary, so
    the stale `Order` object — the one piece of state that actually reaches the wire — is
    gone, and a `cancel_order` on a pre-boundary id is REFUSED rather than transmitted.

    WHAT THE REFUSAL LOOKS LIKE TO THE CALLER, and why it is not the generic "unknown":
    a `BrokerSeamError` naming the session the id belonged to and pointing at
    `query_order_status`, which now reports the order `indeterminate` (§4's third outcome).
    The caller learns that the order exists and cannot be addressed, which is a different
    instruction from "no such order".
    """
    ad, ib, _sink = new_ad()
    await ad.connect()
    ad.place_order(mkt("t10-old", qty=1))
    old_ib_id = ad._to_ib["t10-old"]
    cancels_before = len(ib.cancelled)

    ad.disconnect()
    await ad.connect()
    ad.place_order(mkt("t10-new", qty=1))
    new_ib_id = ad._to_ib["t10-new"]

    # NON-VACUITY: the session really turned over, and the venue really recycled the id.
    # Without the recycling there is no collision to protect against and this traversal
    # would be asserting a refusal that costs nothing.
    nonvac(ib.connect_count == 2, "there was no second session")
    nonvac(
        old_ib_id == new_ib_id,
        f"the fake did not recycle the id ({old_ib_id} vs {new_ib_id})",
    )
    nonvac(
        "t10-new" in ad._orders,
        "the NEW order is not addressable either — this would refuse for the wrong reason",
    )

    # THE REFUSAL. Nothing reaches the wire.
    with pytest.raises(BrokerSeamError, match="has ended"):
        ad.cancel_order("t10-old")
    assert len(ib.cancelled) == cancels_before, (
        f"a cancel reached the wire despite the refusal: {ib.cancelled[cancels_before:]}"
    )

    # NON-VACUITY the other way: the verb still WORKS. A refusal that refuses everything
    # would pass the assertion above and be useless.
    ad.cancel_order("t10-new")
    sent = ib.cancelled[-1]
    assert getattr(sent, "orderId", None) == new_ib_id


# ===========================================================================
# T11 — the data-loss reconcile task racing a disconnect. ADDED SEQUENCE.
# ===========================================================================


@pytest.mark.asyncio
async def test_t11_data_loss_reconcile_publishes_up_after_a_disconnect() -> None:
    """SEQUENCE (ADDED — why: ARC 017 made session state the thing a consumer acts on, so
    a path that publishes a state contradicting the adapter's own is worth probing).

    `_on_data_loss_restore` schedules `_revalidate_then_publish` and returns; the publish
    happens whenever the loop next runs it. Nothing re-checks the session in between. A
    `disconnect()` in that gap is enough.

    PRECONDITIONS: session up; venue emits 1101 (restored with data loss); `disconnect()`
      is called before the scheduled reconcile runs.
    EXPECTED INVARIANT: no UP-class state may be published while the adapter is
      disconnected. `SessionState.is_up` exists precisely so a consumer never has to parse
      prose — its docstring calls it "the canonical spelling of 'is the session usable'".
      Publishing it over a torn-down session makes the canonical spelling wrong, and it
      fails toward RESUMING, which is the direction §14 ("Every uncertainty resolves
      toward flat") forbids.
    OBSERVABLE: the session stream's LAST entry, and `ad._connected` at that moment.
    ACTUAL: `_rebuild_mirror` -> `query_positions` -> `_require_session` raises
      `BrokerNotConnected`; `_rebuild_mirror` catches it and returns False; the caller
      then publishes `UP_DATA_LOSS` regardless, because the rebuild verdict only selects
      the `reason` STRING and never gates the publish. The sink's last session event is
      therefore UP_DATA_LOSS, with `is_up` True, over `_connected is False`.
    §7.12 for this assertion: it would pass vacuously if the reconcile task never ran, so
      the traversal asserts DOWN was published first and that the task then RAN TO
      COMPLETION. "Published nothing" is only a finding about the gate if the thing that
      would have published genuinely executed.

    FINDING T3-02b — REPAIRED IN ARC 020 (A3, D1.25). The `strict=True` xfail is removed in
    the same motion as the fix. Two mechanisms now stand between this task and the sink,
    and both are asserted: the deferred publish re-checks the SESSION EPOCH it was
    scheduled in (not merely `_connected`, which cannot tell "my session" from "a different
    session that is also up"), and `_publish_session` — the single emission point every
    session event now goes through — refuses any UP-class state while `_connected` is False.
    """
    ad, ib, sink = new_ad()
    await ad.connect()
    nonvac(sink.sessions[-1][0] is SessionState.UP, "no UP was published on connect")

    ib.push_error(-1, 1101, "Connectivity restored - data lost")
    nonvac(ad._mirror_stale is True, "the 1101 path did not run")
    nonvac(len(ad._reconcile_tasks) == 1, "no reconcile task was scheduled")

    ad.disconnect()
    nonvac(sink.sessions[-1][0] is SessionState.DOWN, "disconnect did not publish DOWN")
    down_at = len(sink.sessions) - 1

    await spin()
    # NON-VACUITY, and it is the load-bearing one here: the task RAN. A gate asserted over
    # a task that never executed is measuring nothing at all (§7.12 answer V1).
    nonvac(not ad._reconcile_tasks, "the reconcile task never ran")

    assert len(sink.sessions) == down_at + 1, (
        f"the deferred reconcile published over a torn-down session: "
        f"{sink.sessions[down_at:]}"
    )
    last_state, last_reason = sink.sessions[-1]
    assert not (last_state.is_up and ad._connected is False), (
        f"published {last_state.value!r} (is_up={last_state.is_up}, "
        f"reason={last_reason!r}) while _connected={ad._connected}"
    )
    assert last_state is SessionState.DOWN

    # NON-VACUITY the other way: the SAME path DOES publish when the session survives. A
    # gate that refuses everything passes the assertion above and has broken the 1101
    # reconciliation entirely.
    await ad.connect()
    before = len(sink.sessions)
    ib.push_error(-1, 1101, "Connectivity restored - data lost")
    await spin()
    published = sink.sessions[before:]
    assert [s[0] for s in published] == [SessionState.UP_DATA_LOSS], (
        f"the reconcile no longer publishes over a LIVE session: {published}"
    )


@pytest.mark.asyncio
async def test_t11b_a_dead_sessions_reconcile_cannot_publish_over_a_NEW_session() -> (
    None
):
    """SEQUENCE (ADDED IN ARC 020 — why: §7.12 applied to A3's own repair, and it found a
    gap in the instrument before it found one in the code).

    THE PLANT THAT DID NOT PERTURB. The A3 can-fail removed the epoch check from
    `_revalidate_then_publish` and the suite STAYED GREEN — because `test_t11` above drives
    the DISCONNECTED case, and the choke point `_publish_session` catches that one on its
    own by refusing UP-class states while `_connected` is False. Two mechanisms, one
    observable, and the weaker one was sufficient for every sequence being driven. That is
    debug.md failure mode #1 (same verdict for plant and control) about a brand-new gate,
    and §7.12's point exactly: a gate can be right and still be measuring nothing.

    THE SEQUENCE ONLY THE EPOCH CHECK CAN SURVIVE. The reconcile is scheduled in session N,
    session N ends, session N+1 is established — and N+1 is UP, so `_connected` is True and
    the choke point has nothing to object to. The dead session's task then completes and
    would publish `UP_DATA_LOSS` over a session that has just done its own §4 cold-start
    re-read and published a clean `UP`. A consumer would be told to reconcile because of a
    gap in a session it never traded in — and, worse, the state would read as data loss
    over a mirror that IS venue-backed, which is the fail-toward-resuming direction
    inverted into a fail-toward-noise.

    A BARE `if self._connected` CANNOT EXPRESS THIS, which is why `_session_seq` exists and
    is incremented on every boundary in BOTH directions: liveness is not identity.

    PRECONDITIONS: session N up; 1101 raised; the reconcile blocked INSIDE the venue read;
      session N torn down and session N+1 established while it is blocked.
    OBSERVABLE: the session stream after the blocked read is released.
    """
    ad, ib, sink = new_ad()
    await ad.connect()
    gated = GatedIB(ib)
    ad._ib = gated

    ib.push_error(-1, 1101, "Connectivity restored - data lost")
    nonvac(len(ad._reconcile_tasks) == 1, "no reconcile task was scheduled")
    await gated.entered.wait()

    # NON-VACUITY: the dead session's read is genuinely IN FLIGHT, not finished.
    nonvac(gated.completions == [], "the reconcile read already completed")
    scheduled_epoch = ad._session_seq

    ad._ib = ib  # the new session uses the ungated fake; the blocked read keeps `gated`
    ad.disconnect()
    await ad.connect()

    # NON-VACUITY: this is the case the choke point CANNOT see. The adapter is UP, so
    # `_publish_session` would accept an UP-class state; only identity distinguishes them.
    nonvac(ad._connected is True, "the new session is not up — this is test_t11's case")
    nonvac(
        ad._session_seq != scheduled_epoch,
        f"the session epoch did not move ({scheduled_epoch} -> {ad._session_seq}), so "
        "there is nothing for the identity check to discriminate",
    )
    nonvac(
        sink.sessions[-1][0] is SessionState.UP,
        f"the new session did not publish a clean UP: {sink.sessions[-1]}",
    )
    before = len(sink.sessions)
    mirror_before = dict(ad._mirror)

    gated.snapshots = [[ib.position_row("ZZZZ", 9, 1.0)]]
    gated.release.set()  # the DEAD session's read finally answers
    await spin()
    # Derived, not a literal: `GatedIB` inherits `reqpos_calls` from the fake it wraps and
    # connect()'s own rebuild already consumed one, so the call NUMBER is not 1 (§7.4 —
    # never anchor to a number that describes the current state of the world).
    nonvac(
        len(gated.completions) == 1,
        f"the dead session's read never completed: {gated.completions}",
    )

    assert len(sink.sessions) == before, (
        f"a reconcile scheduled in session {scheduled_epoch} published over session "
        f"{ad._session_seq}: {sink.sessions[before:]}"
    )
    assert sink.sessions[-1][0] is SessionState.UP, (
        "the clean UP of the new session was superseded by a dead session's verdict"
    )
    assert ad._mirror_stale is False, (
        "a dead session's rebuild verdict was written onto the LIVE session's flag"
    )
    # And A5's ordering guard holds across the same sequence: the dead session's snapshot
    # was issued FIRST and resolved LAST, so it must not have reached the mirror either.
    assert "ZZZZ" not in ad._mirror and dict(ad._mirror) == mirror_before, (
        f"the dead session's position snapshot reached the live mirror: {ad._mirror}"
    )


# ===========================================================================
# T12 — two overlapping venue reads. ADDED SEQUENCE.
# ===========================================================================


@pytest.mark.asyncio
async def test_t12_overlapping_position_reads_lose_the_newer_snapshot() -> None:
    """SEQUENCE (ADDED — why: the adapter creates a second, concurrent `query_positions`
    itself. `_on_data_loss_restore` schedules one on a bare task while a caller's
    cold-start `query_positions` (§4 makes that call mandatory) may already be in flight.
    Two concurrent reads is a shape this module produces, not one a caller has to invent).

    PRECONDITIONS: session up; the venue's read is gated so two calls overlap and complete
      in a controlled order. Read #1 answers FLAT; read #2, issued later, answers +3.
      Read #2 completes FIRST; read #1 completes second.
    EXPECTED INVARIANT: the mirror must reflect the LAST-COMPLETED venue read. A read
      whose answer was superseded before it was applied must not overwrite the newer one.
      This is the ordinary lost-update invariant and it is not an invented one: the same
      file already guards the ADJACENT case, snapshotting `_seen_execs` across the await
      so "a fill landing between the request and the assignment would be silently erased"
      cannot happen. Fills are guarded; a concurrent read of the same field is not.
    OBSERVABLE: `ad._mirror` after both reads, against `gated.completions` which records
      the true completion ORDER (debug.md §7.7 — verdict by verdict, never in aggregate;
      the two reads' end states are otherwise indistinguishable).
    §7.12 for this assertion: it would pass vacuously if the reads did not actually
      overlap, so entry and completion order are both asserted from the fake's own record.

    FINDING T3-10 — REPAIRED IN ARC 020 (A5, D1.26). The `strict=True` xfail is removed in
    the same motion as the fix. Every `query_positions` takes a monotonic sequence number
    BEFORE it awaits; on resolution it writes `_mirror` only if its number is the highest
    that has yet resolved. Serialising the reads behind a lock was rejected: it would make
    one read WAIT for another, and `_rebuild_mirror`'s completion is what clears
    `_mirror_stale`, which is what `flatten` sizes against (§2A: `flatten` must not block).
    The returned LIST is deliberately not guarded — a caller gets the snapshot it asked
    for; the guard protects the SHARED field two readers can corrupt for each other.
    """
    ad, ib, _sink = new_ad()
    await ad.connect()

    gate1, gate2 = asyncio.Event(), asyncio.Event()
    entered: list[int] = []
    completed: list[int] = []

    async def two_phase():
        n = len(entered) + 1
        entered.append(n)
        await (gate1 if n == 1 else gate2).wait()
        completed.append(n)
        return [] if n == 1 else [ib.position_row("MESU6", 3, 7773.50)]

    ib.reqPositionsAsync = two_phase
    first = asyncio.create_task(ad.query_positions())
    await spin()
    second = asyncio.create_task(ad.query_positions())
    await spin()

    # NON-VACUITY: both reads are genuinely in flight, neither has completed.
    nonvac(entered == [1, 2], f"the two reads did not overlap: entered={entered}")
    nonvac(
        not completed, f"a read completed before the overlap was set up: {completed}"
    )

    gate2.set()  # the NEWER read answers first
    await second
    gate1.set()  # the OLDER read answers second
    stale_result = await first

    nonvac(
        completed == [2, 1], f"completion order was not the one under test: {completed}"
    )

    held = ad._mirror.get("MESU6")
    assert held is not None and held.net_qty == 3, (
        f"mirror={ad._mirror} — the later-completed read (FLAT, issued FIRST) overwrote "
        f"the +3 the venue had already confirmed. flatten() reads this."
    )
    # The stale caller still gets ITS OWN answer, unaltered. The guard protects the shared
    # field, not the return value — conflating the two would silently hand a caller
    # somebody else's snapshot, which is a different defect in the same place.
    assert stale_result == [], (
        f"the discarded read's own return value was rewritten: {stale_result}"
    )


# ===========================================================================
# T13 / T14 — §5.3 bounds and §5.5 corner cases on the protective path.
# ===========================================================================


@pytest.mark.asyncio
async def test_t13_flatten_bounds_empty_absent_and_zero() -> None:
    """BOUNDS (debug.md §5.3): flatten at minimum — empty mirror, absent symbol, zero qty.

    PRECONDITIONS: session up; three cases driven over one adapter.
    EXPECTED: clean handling at every edge, with nothing undefined beyond them (§5.3:
      "Undefined is a certification failure, not a finding to note").
    OBSERVABLE: `ib.placed` per case, and whether anything is raised.

    FINDING T3-11 — CODE DEFECT (minor), debug.md failure mode #11, "silent refusal:
    correct rejection with no observable". `flatten("MESU6")` for a symbol the mirror does
    not hold returns None, places nothing, raises nothing and logs nothing. On the
    PROTECTIVE path the two possible meanings — "already flat" and "the mirror has lost
    this position" — are indistinguishable to the caller, and this adapter has a flag
    (`_mirror_stale`) that already knows which world it may be in. Contrast the
    per-symbol failure path a few lines below in the same method, which collects failures
    and raises with the full picture. VERIFY-AND-CHECKS C.7 ("fail closed and loud")
    applies. Disposition: debt row naming ARC 020 — the right signal is a consumer
    question and D1.20's consumer obligation is the place it belongs.
    """
    ad, ib, sink = new_ad()
    await ad.connect()

    # minimum: an empty mirror. flatten-all must be a clean no-op, not an error.
    nonvac(ad._mirror == {}, "the mirror was not empty at the minimum bound")
    ad.flatten()
    assert not ib.placed

    # just outside: a symbol that is not held. Silent — this is the finding.
    ad.flatten("MESU6")
    assert not ib.placed
    assert not sink.sessions[1:], f"an event was emitted after all: {sink.sessions[1:]}"

    # the zero row: IBKR's "no longer held" notification must not become a flatten of 0.
    ib.push_position("MESU6", 1, 7773.50)
    ib.push_position("MESU6", 0, 0.0)
    nonvac("MESU6" not in ad._mirror, "the zero row was not filtered out of the mirror")
    ad.flatten("MESU6")
    assert not ib.placed

    # and the one case that must fire, so the three no-ops above are not a dead scope.
    ib.push_position("MESU6", -2, 7773.50)
    ad.flatten("MESU6")
    assert len(ib.placed) == 1
    assert ib.placed[0][1].action == "BUY" and int(ib.placed[0][1].totalQuantity) == 2


@pytest.mark.asyncio
async def test_t14_teardown_publishes_one_edge_per_transition() -> None:
    """CORNER CASE (debug.md §5.5): "the operation performed twice — idempotence is a
    property, and it must be proven, not hoped for."

    PRECONDITIONS: session up.
    OBSERVABLE: the session event stream across two `disconnect()` calls, and across a
      `disconnect()` on an adapter that was never connected.

    FINDING T3-12 — REPAIRED IN ARC 020 (A6, D1.28(c)). What this traversal previously
    recorded: `disconnect()` emitted `on_session(DOWN)` on EVERY call including when there
    had never been a session, while §2A defines `on_session(up|down, reason?)` as
    "connectivity **transitions**". A consumer counting edges — and §4's cold-start is
    driven by this edge — saw events reporting no change. The direction was safe (fails
    toward halted), which is why it was characterisation rather than an alarm, and why the
    repair waited for a decision rather than being taken as obvious.

    WHAT IS TRUE NOW: the TEARDOWN is still unconditional and still best-effort — the
    vendor call is attempted every time, the local state is dropped every time. Only the
    EMISSION is edge-correct, and it is enforced at the single choke point
    (`_publish_session`) rather than in this verb, so no future emission site can reopen
    it. UP-class states are deliberately NOT collapsed the same way: a repeated
    `UP_DATA_LOSS` carries a fresh reconciliation obligation each time.
    """
    ad, _ib, sink = new_ad()
    await ad.connect()
    nonvac(sink.sessions[-1][0] is SessionState.UP, "no UP was published")

    ad.disconnect()
    ad.disconnect()
    downs = [s for s in sink.sessions if s[0] is SessionState.DOWN]
    assert len(downs) == 1, f"expected one DOWN per TRANSITION, got {downs}"

    # NON-VACUITY: the teardown itself still ran both times. This is a claim about the
    # EVENT stream, not about the verb becoming a no-op.
    assert ad._connected is False and ad._startup_complete is False

    # ...and the edge re-arms: a genuine UP -> DOWN transition still publishes.
    await ad.connect()
    nonvac(sink.sessions[-1][0] is SessionState.UP, "the session did not come back up")
    ad.disconnect()
    assert len([s for s in sink.sessions if s[0] is SessionState.DOWN]) == 2, (
        f"the DOWN edge did not re-arm after a new session: {sink.sessions}"
    )

    # A teardown with no session before it is not a transition at all.
    fresh, _ib2, sink2 = new_ad()
    fresh.disconnect()
    assert sink2.sessions == [], (
        f"a DOWN was published for a session that never existed: {sink2.sessions}"
    )
    with pytest.raises(BrokerNotConnected):
        fresh.flatten()


# ===========================================================================
# T15 — §5.4 scale. Resource growth, measured rather than extrapolated.
# ===========================================================================


@pytest.mark.asyncio
async def test_t15_per_order_state_is_never_released() -> None:
    """SCALE (debug.md §5.4): "anything per-item that is not released is a leak that only
    appears at scale."

    PRECONDITIONS: session up; N complete order lifecycles (place -> fill -> Filled),
      each opened and closed so nothing is left working.
    EXPECTED INVARIANT: this adapter lives inside a daemon the spec requires to run
      continuously (§12 "Non-Stop Operation"; §13 item 22 is a multi-day soak asserting
      "memory/fd stability"). Per-order state for orders that reached a terminal state and
      can never be referenced again should not grow without bound.
    OBSERVABLE: the sizes of the six per-order maps, asserted as a RELATION to N (§7.4 —
      never a literal, and never a ceiling copied from a previous run).
    FINDING T3-13 — REPAIRED IN ARC 020 (A1(ii), D1.24). Before this arc all seven maps
    grew linearly with the number of orders EVER placed and none was ever pruned, and
    `_orders` retaining terminal orders is the specific retention that made T3-01b
    (test_t10) reachable — so the repair was shared and was never purely hygienic.

    THE RETENTION POLICY, which the debt row is explicit is "a §4 question, not a free
    deletion". Per-order state for a TERMINAL order is released after
    `terminal_order_retention_ms` (config; DERIVED from §12A:830's `PENDING_ACK_TIMEOUT_MS`
    and `FILL_TIMEOUT`, and boot-validated to exceed both). It cannot be zero for two
    independent reasons: §4 resolves a pending timeout by QUERYING order status, so the
    order must outlive the interval before the Limiter asks; and §4 "Partial fill"
    anticipates an execution arriving AFTER a terminal transition ("if the cancel loses
    the race and the remainder fills").

    WHAT THIS TRAVERSAL ASSERTS, in two halves, because either alone is satisfiable by a
    defect: that the window genuinely HOLDS the state (a release policy that dropped
    everything immediately would break §4's query), and that the state is genuinely
    RELEASED once the window passes (the growth bound). The clock is MOVED rather than
    waited on — debug.md failure mode #6 — so this has no wall-clock dependency and cannot
    go stale if the configured retention changes.
    """
    ad, ib, sink = new_ad()
    await ad.connect()

    n = 200
    for i in range(n):
        cid = f"t15-{i}"
        ad.place_order(mkt(cid, qty=1, side=Side.BUY if i % 2 == 0 else Side.SELL))
        trade = ib.placed[-1][2]
        ib.push_exec(
            trade, f"t15-e{i}", 1, 7773.50, 1, side="BOT" if i % 2 == 0 else "SLD"
        )
        ib.push_status(trade, "Filled", filled=1)

    nonvac(len(sink.fills) == n, f"only {len(sink.fills)} of {n} lifecycles ran")
    nonvac(
        all(ad.query_order_status(f"t15-{i}").terminal for i in range(n)),
        "not every order reached a terminal state",
    )
    # The mirror DOES net out — alternating sides close each other. So what is measured
    # below is per-order bookkeeping, not "positions are open".
    nonvac(ad._mirror == {}, f"the positions did not net flat: {ad._mirror}")

    def sizes() -> dict[str, int]:
        return {
            "_neutral": len(ad._neutral),
            "_orders": len(ad._orders),
            "_trades": len(ad._trades),
            "_to_ib": len(ad._to_ib),
            "_from_ib": len(ad._from_ib),
            "_acked": len(ad._acked),
            "_seen_execs": len(ad._seen_execs),
        }

    # HALF ONE — inside the window the state is RETAINED, and is retained BECAUSE §4 needs
    # it, not by accident. All n orders are terminal and all n are still queryable.
    within = sizes()
    assert all(v == n for v in within.values()), (
        f"per-order state inside the retention window: {within} — expected {n} of each. "
        "A release before the window closes breaks §4's pending-timeout query"
    )
    assert len(ad._retire_queue) == n, (
        f"only {len(ad._retire_queue)} of {n} terminal orders were SCHEDULED for release "
        "— the rest would never be released at all"
    )

    # HALF TWO — age every scheduled release past the window and let the next order-path
    # call sweep. The sweep point is `place_order`: no timer, no task.
    aged = deque(
        (ts - (ad._cfg.terminal_order_retention_ms / 1000.0) - 1.0, cid)
        for ts, cid in ad._retire_queue
    )
    ad._retire_queue = aged
    ad.place_order(mkt("t15-sweep", qty=1))

    after = sizes()
    assert all(v <= 1 for v in after.values()), (
        f"per-order state after the retention window expired: {after} — expected at most "
        "the one sweeping order in each map"
    )
    assert not ad._retire_queue, f"the retire queue did not drain: {ad._retire_queue}"
    # And the released orders now answer `unknown` — no record at all — which is the
    # correct answer once retention has expired and is distinguishable from the
    # `indeterminate` a session boundary produces (test_t5b).
    assert ad.query_order_status("t15-0").state == "unknown"
