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
async def test_t1_flatten_twice_fires_twice() -> None:
    """SEQUENCE: two concurrently-scheduled `flatten()` calls over one mirrored position.

    PRECONDITIONS: session up, mirror holds MESU6 +2 from a positionEvent.
    OBSERVABLE: `ib.placed`, and a per-fan-out sample of `ad._mirror` taken from an
      instrumented contract resolver.

    WHAT IS DETERMINED, and asserted: `flatten()` is sync and contains no `await`, so it
    is ATOMIC with respect to the loop. Neither call can observe the other's partial
    work, and each therefore reads the SAME mirror — `place_order` does not decrement it,
    only a fill does. So N calls emit N opposing orders each sized at the full held
    quantity. Asserted as a relation derived from the inputs (calls x held qty), never as
    a literal, per debug.md §7.4.

    FINDING T3-04 — SPEC GAP, not a code defect. Two protective flattens over one +2
    position emit -4 of market orders. §2A line 68 defines `flatten(symbol | all)` as
    "market-close a position (protective path; must not block)" and says nothing about
    repeat invocation; debug.md §5.5 requires idempotence to be PROVEN, not hoped for,
    and it is not a property this adapter has. The adapter's own docstring calls itself
    'dumb hands' and puts serialisation on the Limiter — but §4's protective exits are
    listed as SIX independent triggers ("stop / stale / floor / session / uncertainty /
    orphan") and are "unconditional", so two of them firing in one cycle is a designed
    shape, not a caller error. §4's "one in-flight action per strategy" governs STRATEGY
    signals, not Limiter-side protective exits.
    THE SECTION THAT WOULD HAVE TO SAY: §2A broker-order commands (the `flatten` bullet),
    or §4 "Exits (dual authority)". Neither currently does. NOT INVENTED HERE.
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

    # NON-VACUITY: both calls really reached the fan-out, and both really read +2. If the
    # first had decremented the mirror the second sample would differ and this traversal
    # would be reporting on a sequence that did not happen.
    nonvac(len(seen_at_fanout) == 2, f"fan-out ran {len(seen_at_fanout)} times, not 2")
    nonvac(
        seen_at_fanout == [2, 2],
        f"the two flattens did not read the same mirror: {seen_at_fanout}",
    )

    flats = [o for _c, o, _t in ib.placed]
    calls, held = 2, 2
    assert len(flats) == calls
    assert sum(int(o.totalQuantity) for o in flats) == calls * held
    assert all(o.action == "SELL" for o in flats)
    # Distinct ids: the ONE thing the adapter does guarantee across repeats.
    ids = [cid for cid, _s, _r, _rc in sink.acks] or list(ad._neutral)
    assert len(set(ids)) == len(ids)


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
    nonvac(
        ib_id in ad._from_ib,
        "disconnect cleared the id map — the loud branch is unreachable",
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


@pytest.mark.xfail(
    strict=True,
    reason=(
        "FINDING T3-02 (CODE DEFECT): query_order_status returns a cached pre-disconnect "
        "status across a session boundary. §4's pending-timeout path must resolve "
        "confirmed / cancelled / INDETERMINATE; this adapter has no way to say "
        "indeterminate and answers 'working' for an order whose session is gone."
    ),
)
@pytest.mark.asyncio
async def test_t5b_order_status_is_stale_across_a_session_boundary() -> None:
    """SEQUENCE: place an order, lose the session, reconnect, ask for its status.

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


@pytest.mark.xfail(
    strict=True,
    reason=(
        "FINDING T3-01 (CODE DEFECT, most severe): a connect() cancelled during the "
        "mirror rebuild leaves _connected=True and _startup_complete=False — the adapter "
        "accepts orders and silently drops every ack and fill for them, forever."
    ),
)
@pytest.mark.asyncio
async def test_t6b_cancelled_connect_leaves_a_deaf_but_accepting_adapter() -> None:
    """SEQUENCE: `asyncio.wait_for(connect(), t)` times out during the mirror rebuild.

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


@pytest.mark.asyncio
async def test_t6c_cancelled_connect_the_evidence() -> None:
    """The BEHAVIOURAL half of FINDING T3-01, asserted as observed fact.

    T3-01's xfail above states the invariant. This states what actually happens, so the
    finding is evidenced rather than only claimed, and so the triage in Phase 4 can see
    the blast radius without re-deriving it. debug.md §7.9: PASS/FAIL/CANNOT-MEASURE must
    be distinguishable, and "the adapter accepted the order" is a measured PASS of the
    wrong thing.

    OBSERVABLE: `ib.placed` (the order reached the venue) and `sink.fills`/`sink.acks`
    (nothing came back), with the loud-drop log as corroboration.
    """
    ad, ib, sink = new_ad()
    gated = GatedIB(ib)
    ad._ib = gated
    task = asyncio.create_task(ad.connect())
    await gated.entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    nonvac(
        ad._connected is True and ad._startup_complete is False, "window not reached"
    )
    nonvac(
        not sink.sessions, f"a session event was published after all: {sink.sessions}"
    )

    ad._ib = ib  # the transport is fine; only the adapter's state is wrong
    ad.place_order(mkt("t6c-buy", qty=1))
    trade = ib.placed[-1][2]
    ib.push_status(trade, "Submitted")
    ib.push_exec(trade, "t6c-e1", 1, 7773.50, 1, side="BOT")

    assert len(ib.placed) == 1, "the order did NOT reach the venue"
    assert not sink.acks, f"an ack escaped the shut gate: {sink.acks}"
    assert not sink.fills, f"a fill escaped the shut gate: {sink.fills}"
    assert ad._mirror == {}, "the mirror moved despite the gate being shut"


# ===========================================================================
# T7 — flatten() during a reconnect. Protective path over an unrebuilt mirror.
# ===========================================================================


@pytest.mark.asyncio
async def test_t7_flatten_during_reconnect_fires_into_a_shut_gate() -> None:
    """SEQUENCE: a protective `flatten()` is issued while `connect()` awaits the rebuild.

    PRECONDITIONS: a first session established and dropped; the mirror still holds the
      previous session's MESU6 +1; a second `connect()` gated inside `_rebuild_mirror`.
    OBSERVABLE: `ib.placed` (did the protective path fire), and the sink (was anything
      about those orders ever reported).

    WHAT IS DETERMINED, and asserted: the protective path DOES fire — `_require_session`
      passes because `_connected` is set before the rebuild — and every ack and fill for
      the orders it fires is refused by the still-shut startup gate. §14's "The
      exit/protective path has zero wire/delivery dependency" is honoured in the sense
      that flatten did not block; it is not honoured in the sense that matters, because
      the outcome of the protective action is unobservable to the consumer.

    FINDING T3-05 — SPEC GAP. Whether a protective flatten may run during session
    re-establishment is undetermined. §4 "Boot / known-state discipline" forbids strategy
    REGISTRATION before reconciliation and says the cold-start query "gates registration";
    it says nothing about a Limiter-side protective exit fired while a session is being
    re-established — which is exactly when one is most likely (a stop hit while the
    session was down). §14 says "execution of any flatten is Limiter-only" and that the
    exit path has zero wire dependency, which reads as licence to fire; the adapter's
    startup gate reads as licence to discard the result. Both are defensible and the spec
    does not choose. NOT INVENTED HERE.
    THE SECTION THAT WOULD HAVE TO SAY: §4 "Boot / known-state discipline", or §2A's
    `flatten` bullet. Neither addresses re-establishment.
    """
    ad, ib, sink = new_ad()
    await ad.connect()
    ib.push_position("MESU6", 1, 7773.50)
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

    placed_before = len(ib.placed)
    ad._ib = ib  # orders go to the real fake; the rebuild stays gated
    ad.flatten()
    fired = ib.placed[placed_before:]
    assert len(fired) == 1 and fired[0][1].action == "SELL"

    trade = fired[0][2]
    ib.push_status(trade, "Submitted")
    ib.push_exec(trade, "t7-e1", 1, 7773.00, 1, side="SLD")
    assert not sink.acks, f"the shut gate let an ack through: {sink.acks}"
    assert not sink.fills, f"the shut gate let a fill through: {sink.fills}"

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

    FINDING T3-08 — WORKING AS INTENDED BUT SURPRISING, with a real edge. `connect()`
    clears `_to_ib`, `_from_ib`, `_acked` and `_cancelled` because "session boundary
    invalidates every IBKR-side id" — but not `_neutral`, `_orders`, `_trades` or
    `_seen_execs`. So the NEUTRAL id space is permanently consumed for the life of the
    process while the VENDOR id space is reset. A Limiter minting deterministic ids
    (strategy+sequence) is blocked after a Gateway restart even though nothing about that
    id means anything at the venue any more. The asymmetry is not stated anywhere; the
    comment at the clear site explains why the vendor ids go and is silent on why the
    neutral ones stay. Disposition: debt row naming ARC 020 — it needs an id-lifetime
    decision, not a one-line fix, and it shares a repair with T3-01/T3-02/T3-09.
    """
    ad, ib, sink = new_ad()
    await ad.connect()
    ad.place_order(mkt("t8-buy", qty=1))
    trade = ib.placed[-1][2]
    ib.push_exec(trade, "t8-e1", 1, 7773.50, 1, side="BOT")
    ib.push_status(trade, "Filled", filled=1)

    nonvac(len(sink.fills) == 1, "the order never completed")
    nonvac(ad.query_order_status("t8-buy").terminal, "the order is not terminal")

    with pytest.raises(BrokerSeamError, match="duplicate client_order_id"):
        ad.place_order(mkt("t8-buy", qty=1))

    ad.disconnect()
    await ad.connect()
    nonvac(ib.connect_count == 2, "no second session")
    nonvac(not ad._from_ib, "the vendor id map survived the boundary")

    # The asymmetry, asserted as a relation rather than a count.
    assert "t8-buy" in ad._neutral and "t8-buy" in ad._orders and "t8-buy" in ad._trades
    with pytest.raises(BrokerSeamError, match="duplicate client_order_id"):
        ad.place_order(mkt("t8-buy", qty=1))


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


@pytest.mark.xfail(
    strict=True,
    reason=(
        "FINDING T3-01b (CODE DEFECT, high): _orders survives connect() while IBKR order "
        "ids reset, so cancel_order() on a stale id sends a cancel carrying an orderId "
        "that now belongs to a DIFFERENT live order in the new session."
    ),
)
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
    """
    ad, ib, _sink = new_ad()
    await ad.connect()
    ad.place_order(mkt("t10-old", qty=1))
    old_ib_id = ad._to_ib["t10-old"]

    ad.disconnect()
    await ad.connect()
    ad.place_order(mkt("t10-new", qty=1))
    new_ib_id = ad._to_ib["t10-new"]

    # NON-VACUITY: the session really turned over, and the venue really recycled the id.
    nonvac(ib.connect_count == 2, "there was no second session")
    nonvac(
        old_ib_id == new_ib_id,
        f"the fake did not recycle the id ({old_ib_id} vs {new_ib_id})",
    )
    nonvac("t10-old" in ad._orders, "the stale order object was cleared after all")

    ad.cancel_order("t10-old")
    sent = ib.cancelled[-1]
    assert getattr(sent, "orderId", None) != new_ib_id, (
        f"cancel_order('t10-old') put orderId {getattr(sent, 'orderId', None)} on the "
        f"wire, which is the live venue id of 't10-new' in this session"
    )


# ===========================================================================
# T11 — the data-loss reconcile task racing a disconnect. ADDED SEQUENCE.
# ===========================================================================


@pytest.mark.xfail(
    strict=True,
    reason=(
        "FINDING T3-02b (CODE DEFECT, high): the 1101 reconcile task publishes an "
        "UP-class session state after disconnect() has already published DOWN, so "
        "state.is_up reads True over a session the adapter knows is closed."
    ),
)
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
      the traversal asserts DOWN was published first and that the task then completed.
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
    nonvac(not ad._reconcile_tasks, "the reconcile task never ran")
    nonvac(len(sink.sessions) > down_at + 1, "the reconcile published nothing")

    last_state, last_reason = sink.sessions[-1]
    assert not (last_state.is_up and ad._connected is False), (
        f"published {last_state.value!r} (is_up={last_state.is_up}, "
        f"reason={last_reason!r}) while _connected={ad._connected}"
    )


# ===========================================================================
# T12 — two overlapping venue reads. ADDED SEQUENCE.
# ===========================================================================


@pytest.mark.xfail(
    strict=True,
    reason=(
        "FINDING T3-10 (CODE DEFECT): query_positions assigns self._mirror wholesale "
        "with no ordering guard, so two overlapping reads leave the mirror holding the "
        "EARLIER-completed snapshot — a lost update on the protective path's only input."
    ),
)
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
    await first

    nonvac(
        completed == [2, 1], f"completion order was not the one under test: {completed}"
    )

    held = ad._mirror.get("MESU6")
    assert held is not None and held.net_qty == 3, (
        f"mirror={ad._mirror} — the later-completed read (FLAT, issued FIRST) overwrote "
        f"the +3 the venue had already confirmed. flatten() reads this."
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
async def test_t14_teardown_is_not_idempotent() -> None:
    """CORNER CASE (debug.md §5.5): "the operation performed twice — idempotence is a
    property, and it must be proven, not hoped for."

    PRECONDITIONS: session up.
    OBSERVABLE: the session event stream across two `disconnect()` calls, and across a
      `disconnect()` on an adapter that was never connected.

    FINDING T3-12 — WORKING AS INTENDED BUT SURPRISING. `disconnect()` is unconditional:
    it emits `on_session(DOWN)` every time it is called, including when there was never a
    session. A consumer counting transitions, or acting on the DOWN edge (§4's cold-start
    is driven by `on_session`), sees an event that reports no change. It fails toward
    halted, which is the safe direction, so this is characterisation rather than an alarm.
    §2A defines `on_session(up|down, reason?)` as "connectivity TRANSITIONS" — a repeat
    DOWN is not a transition, so the wording is at least in tension with the behaviour.
    Disposition: debt row naming ARC 020, low priority; it pairs with the edge-vs-level
    distinction already recorded for `_mirror_stale`.
    """
    ad, _ib, sink = new_ad()
    await ad.connect()
    nonvac(sink.sessions[-1][0] is SessionState.UP, "no UP was published")

    ad.disconnect()
    ad.disconnect()
    downs = [s for s in sink.sessions if s[0] is SessionState.DOWN]
    assert len(downs) == 2, f"expected one DOWN per call, got {downs}"

    fresh, _ib2, sink2 = new_ad()
    fresh.disconnect()
    assert [s[0] for s in sink2.sessions] == [SessionState.DOWN]
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
    ACTUAL, and FINDING T3-13 — CODE DEFECT (scale). All six grow linearly with the number
    of orders ever placed, and none is ever pruned. `_seen_execs` grows with executions,
    so a partially-filling instrument grows it faster. Nothing here is a fast leak — a
    per-order tuple is small — but nothing bounds it either, and `_orders` retaining
    terminal orders is the specific retention that makes T3-01b (test_t10) reachable, so
    the repair is shared and is not purely hygienic.
    Disposition: debt row naming ARC 020 — it needs a retention policy (how long must a
    terminal order stay queryable through `query_order_status`?), which is a §4
    pending-timeout question, not a free deletion.
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
    # The mirror DOES net out — alternating sides close each other. So the growth below
    # is not "positions are open"; it is per-order bookkeeping with no release.
    nonvac(ad._mirror == {}, f"the positions did not net flat: {ad._mirror}")

    sizes = {
        "_neutral": len(ad._neutral),
        "_orders": len(ad._orders),
        "_trades": len(ad._trades),
        "_to_ib": len(ad._to_ib),
        "_from_ib": len(ad._from_ib),
        "_acked": len(ad._acked),
        "_seen_execs": len(ad._seen_execs),
    }
    assert all(v == n for v in sizes.values()), (
        f"per-order state after {n} CLOSED lifecycles, all flat: {sizes} — every map "
        "retains one entry per order ever placed, with no release path"
    )
