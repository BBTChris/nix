"""
test_datafeed_tier3.py — TIER-3 TRAVERSAL of the IBKR broker-datafeed adapter (debug.md §5).

A DISCOVERY instrument, not a regression suite. `test_broker_datafeed.py` already owns the
per-behaviour properties of this adapter (Tier 1/2: did this change break something). This file
owns the property that file does not assert and structurally cannot: **what the module does
across its pathways, in combination, in the order a real caller would use them** — debug.md
§5.1:408-410's *"the sequences nobody designs for: the same operation twice, operations
interleaved, an operation retried after a partial failure, a caller that abandons midway"* —
plus §5.3 bounds, §5.4 scale and §5.5 corner cases.

VERIFY-AND-CHECKS Part C.9 ("extend an instrument that already owns a property; never build a
second") is satisfied by that boundary: no assertion below duplicates one in
`test_broker_datafeed.py`. The shared artefacts — `FakeIBFeed` and `bar_row` — are IMPORTED,
never copied, for exactly the C.9 reason: two fakes drift, and a traversal driven against a
drifted fake measures a venue that does not exist. `_FIDELITY` asserts at import that the fake
still carries the surface these traversals drive, so drift fails collection instead of silently
narrowing scope. It is the datafeed counterpart of `test_broker_tier3.py`'s `_FIDELITY`, reached
the same way and deliberately not shared with it (invariant 3: the two libraries' instruments
stay independent for the same reason the libraries do).

--------------------------------------------------------------------------------------
WHAT A FINDING LOOKS LIKE HERE. `test_broker_tier3.py`'s three encodings, used unchanged, plus
ONE DECLARED EXTENSION which is flagged as an extension rather than smuggled in:

  1. `@pytest.mark.xfail(strict=True)` — the outcome IS determined by an authority outside
     this file and the adapter violates it. strict, so the day someone repairs it the suite
     goes RED and the finding has to be closed rather than quietly rotting.
  2. A plain assertion on a DERIVED relation — the behaviour is defined, correct, and the
     traversal proves it holds under interleaving / repetition / partial failure.
  3. A plain assertion on OBSERVED behaviour plus `SPEC GAP` in the docstring — the spec does
     not determine the answer. Per the arc brief the correct output is the finding and the
     SECTION THAT WOULD HAVE TO SAY, never an invented invariant. Nothing below encodes an
     invented answer as an assertion.

  THE EXTENSION (declared, ARC 022): several findings here are **code defects that no spec
  determines** — the adapter contradicts a rule IT ITSELF states, in its own docstring, about
  its own field. That is neither a spec gap (the answer is not missing; the module wrote it
  down) nor spec-determined (the frozen document is silent). Those carry encoding 3's SHAPE —
  assert the observed behaviour, do not invent the remedy — under the label
  `FINDING — INTERNAL CONTRADICTION`, and they name the module's own sentence as the authority
  they contradict. A fourth encoding was NOT invented; the label is what is new, and it is
  reported as a deviation rather than presented as the convention.

  WHICH AUTHORITIES COUNT AS "DETERMINED" for encoding 1, stated because it decides two
  markers: the frozen `nics_risk_subsystem_spec_v1.3.md`; a ratified operator ruling in
  `docs/SPEC-AMENDMENTS.md` (that file states its rulings have "the authority of an operator
  decision, which is real"); and a runtime guard in `broker_seam.py` whose own docstring
  declares the rule it enforces. Only two xfails below, and each names which of the three.

CITATIONS. Every § below was resolved against the real document before it was written.
Verified anchors, at commit b9a4b00:
  - `debug.md` §5 "TIER 3 — END-OF-MODULE CERTIFICATION"      — line 388
  - `debug.md` §5.1 traversal / §5.3 bounds / §5.4 scale / §5.5 corner cases — 398/420/430/446
  - `debug.md` §7.1 can-fail+CONTROL, §7.3 non-vacuity, §7.4 anchors, §7.6 absence,
    §7.9 fail-closed, §7.12 the standing question — 572/591/603/626/653/679
  - `nics_risk_subsystem_spec_v1.3.md` §2A "Broker Abstraction Contract" — line 53; the
    broker-datafeed subsection at 86-92; the numbered seam invariants at 103-107
  - `nics_risk_subsystem_spec_v1.3.md` §6.4 push-preferred / retry-before-stale — 371-374
  - `docs/SPEC-AMENDMENTS.md` AMENDMENT 3 (+ its ARC 022 refinement), AMENDMENT 4,
    AMENDMENT 5 / D1.38 — all present with the field/status tables this file cites.

--------------------------------------------------------------------------------------
debug.md §7.12 — THE STANDING QUESTION, answered in writing, for this suite as a whole.

  "What would have to be true for `test_datafeed_tier3.py` to pass while measuring nothing?"

Eight conditions, every one of them plantable:

  V1. THE PORT'S VERBS NEVER SUSPEND, SO NOTHING EVER INTERLEAVES — and this one is TRUE
      TODAY. D1.38 made five verbs `async def` and NOT ONE of their bodies contains an
      `await`, so `asyncio.gather` over two of them runs them strictly serially and a
      `Task.cancel()` can never land mid-flight. A concurrency suite written against that
      surface passes every ordering assertion vacuously. DEFENCE, in three parts, because one
      is not enough: `test_guard_async_verbs_have_no_suspension_point` states the fact
      STRUCTURALLY by AST and derives the verb set from `DATAFEED_ASYNC_VERBS` rather than
      listing it; every concurrency traversal asserts the OBSERVED ORDERING out of `EventLog`
      and calls `nonvac()` on the shape it requires; and
      `test_control_interleave_detector_can_see_an_interleave` is the CONTROL — the same
      recorder over two coroutines that DO suspend, proving the detector reports overlap when
      overlap exists. Without that control, "they did not interleave" and "the detector is
      blind" are the same observation.
  V2. THE FAKE STOPS CARRYING THE SURFACE. `FakeIBFeed` and `bar_row` live in
      `test_broker_datafeed.py`. Rename `grant_map`, `bind`, `cancelled` or `subscribed` and
      every driver below degrades to "the adapter was never actually driven". PLANT: rename
      one. DEFENCE: `_FIDELITY`, asserted at module import, fails COLLECTION.
  V3. THE SINK IS NOT THE ONE THE ADAPTER WRITES TO. debug.md §7.12's own eighth instance
      (ARC 016): assertions read a recorder nothing had written to. PLANT: build the adapter
      with one sink and assert on another. DEFENCE: `new_ad()` is the ONLY construction path,
      returns the very objects it injected, and asserts `ad._sink is sink and ad._ib is fake`
      before handing them back.
  V4. THE TRAVERSAL NEVER REACHED THE STATE IT REPORTS ON. Half of these sequences depend on
      being INSIDE a condition — a grant actually held before the re-subscribe that destroys
      it, a bar actually sealed before the tear that loses it. PLANT: delete the first
      `subscribe`, and "the grant is UNKNOWN after re-subscribe" passes for the wrong reason.
      DEFENCE: every such traversal asserts the precondition with `nonvac()` FIRST, and the
      failure text says the traversal did not reach its subject — CANNOT MEASURE, not a
      finding about the adapter (debug.md §7.9).
  V5. A REVISION TRAVERSAL WHOSE TWO POLLS RETURN IDENTICAL DATA. Then "no revision was
      published" is true of a correct adapter and of one that cannot revise at all. PLANT:
      make the second poll's rows equal the first's. DEFENCE: `nonvac()` asserts the two
      payloads genuinely differ before any revision claim, and the NaN traversal carries the
      inverse control (identical rows -> zero revisions) so both directions are demonstrated.
  V6. AN xfail SILENTLY BECOMES AN xpass. PLANT: repair either defect. DEFENCE: both xfails
      are `strict=True`, so an xpass is a FAILURE and the finding must be closed in the same
      motion as the fix.
  V7. THE SCALE TRAVERSAL MEASURES A CONSTANT. A throughput or growth claim asserted against a
      literal is debug.md §7.4's third row. PLANT: hard-code the sample count. DEFENCE: §5.4's
      traversal asserts the RELATION (samples == ticks delivered; the session mean stays inside
      tolerance while the recent window is outside it) and records the measured numbers in
      `MEASURED` for the arc report, asserting on none of them.
  V8. THE HOLLOW CONTROL PASSES BECAUSE THE DRIVERS DRIVE NOTHING. If a traversal's observable
      is empty for both a working adapter and a hollow one, it distinguishes nothing. PLANT:
      point `new_ad()` at `HollowBrokerDatafeed`. DEFENCE:
      `test_control_hollow_adapter_fails_the_traversal_observables` drives the hollow adapter
      through the same sequences and asserts the observables are EMPTY where the real adapter's
      are non-empty — structurally (it satisfies the whole roster) and behaviourally.

CAN-FAIL EVIDENCE, with CONTROL (debug.md §7.1) — recorded here, beside the gate, because the
next person to edit this file is the one who needs it.

  THE NON-VACUITY GUARDS FIRED FOR REAL DURING CONSTRUCTION, which is stronger than a plant:
    - `test_t5_two_overlapping_polls...` — the first draft asserted "one seal per key under
      concurrency" and passed. `nonvac()` on the EventLog then showed the log read
      enter/exit/enter/exit: the two polls had never overlapped, because `poll_history` has no
      suspension point. The traversal was rewritten to assert the ATOMICITY and to report the
      absence of a suspension point as the finding, which is what it actually measured.
    - `test_t14_identical_repoll_carrying_nan...` — the first draft reused ONE row dict across
      polls and observed zero revisions. That is not the adapter being correct: CPython's
      tuple comparison short-circuits on identity, so the same `nan` OBJECT compares equal to
      itself. Rebuilding the row per poll (which is what a real vendor read does) produced a
      revision on every poll. A traversal that had kept the shared dict would have banked a
      clean green over the defect.

    - `EventLog.overlapped` — the third, and the one that would have INVERTED a finding rather
      than merely weakening it. The first spelling used set membership (`{a, b} <= open_now`),
      which is correct for two different labels and WRONG for the case T5 and T9 actually ask
      about: two polls of the SAME symbol, where one open mark satisfies the set and the
      detector reports an overlap that never happened. It fired on T5 as a plain contradiction —
      the mark list read enter/exit/enter/exit and the detector said "overlapped" — and the
      helper was rewritten to count nesting depth. Arm C of the interleave control exists solely
      to keep that direction proven.
    - The hollow control's first draft asserted `granted_mode() is UNKNOWN`. The hollow returns
      REALTIME BY DESIGN — its docstring says so — so the draft was asserting that the control
      does not do the thing it was built to do. Caught on first run, and the control now
      asserts the FABRICATION rather than an emptiness.

  THE CONTROLS, both required and both present: `test_control_interleave_detector_...` (the
  detector is not blind, in three arms) and `test_control_hollow_adapter_...` (the drivers
  really drive).

  THE PLANTS, run ARC 022 at b9a4b00. debug.md §7.2 forbids planting into a production
  artefact, so all three were run against a SCRATCH COPY of `scripts/broker/` outside the
  worktree; the tree's own adapter was never modified, and its sha256 was compared before and
  after (`0e18970287…c402da`, identical). `__pycache__` purged between every step.

    P1  `_ingest_history`: `self._maybe_revise(...)` -> `self._sealed[key] = sealed`, i.e. the
        D1.14 defect itself — rewrite the seal instead of publishing the contradiction.
        CAUGHT: `test_t6_...` FAILED at the sealed-object identity assertion, and
        `test_t14_...` turned into an XPASS(strict) FAILURE because a rewriting adapter never
        reaches the comparison the NaN finding is about. 2 failed / 24 passed.
    P2  `subscribe()`: the `state.granted_mode = MarketDataMode.UNKNOWN` sentinel line deleted
        — the exact defect GAP-D3 and D1.13 exist to prevent.
        CAUGHT: `test_t1_...` and `test_t1b_...` FAILED, naming
        `test_datafeed_tier3.py:673`. 2 failed / 23 passed.
    P3  `_on_ib_tick()`: `state.lag_samples.append(...)` deleted.
        CAUGHT: SIX traversals FAILED — T1b, T7, T7b, T10, T15, T16 — which is the right
        answer, because every one of them rests on an observation actually having been made.
        6 failed / 19 passed.
    CONTROL after each restore: 25 passed / 2 xfailed, byte-identical adapter.

  READ THE THREE AS A SET: no plant reddened the whole file, and none reddened only one test.
  A plant that reddens everything is a suite asserting a global, and a plant that reddens
  nothing is a suite measuring nothing. The blast pattern maps onto the subject each traversal
  claims — which is the discrimination §7.7 asks for, verdict by verdict rather than in
  aggregate.

  ARC 023 — FOUR FINDINGS CLOSED, AND WHAT THAT DID TO THIS FILE. Appended, not rewritten: the
  block above is ARC 022's banked evidence (`CLAUDE.md` directive 6).

    FLIPPED, because the fix made the encoding stale: T11 (F12), T12 (F13), T16 (F17), T19
    (D1.39/D1.40) and T20 (F21). Each keeps its SEQUENCE — the sequence is what proves the
    repair — and its docstring now records what it found, what the repair is, and what is still
    open. NO FINDING WAS DELETED and no new Tier 3 was written.

    SIX TRAVERSALS WERE CAUGHT VACUOUS BY THEIR OWN `nonvac()` GUARDS the moment the lag
    window's SAMPLE FLOOR landed — T1b, T7, T7b, T10, T15 and one arm of T16 drove one to four
    ticks and the floor declares absence below five, so every one of them reported *"the
    traversal never reached its subject"* rather than a false finding about the adapter. That
    is §7.3 working, not a suite that needed repairing, and it is why `saturate()` derives its
    packet count from `LAG_SAMPLE_FLOOR` instead of typing one.

    THE PLANTS, run ARC 023 against a SCRATCH COPY of the whole tree outside the worktree
    (§7.2). The tree's own adapter was never modified and its sha256 was identical before and
    after every one (`9eb19c2cb3…105c175d`). `__pycache__` purged between every step. CONTROL
    after each restore: 109 passed / 2 xfailed across this file and `test_broker_datafeed.py`.

      P1  `_report_for`: the POLL channel branch removed — F21 itself.        3 failed
      P2a `_LagWindowStore.record`: both trims removed (unbounded again).     3 failed
      P2b `windowed_mean_s`: the sample floor removed.                       12 failed
      P2c `windowed_mean_s`: returns the SESSION mean — F17's exact inversion. 2 failed
      P3a the publication debt is discarded as soon as it is added.          18 failed
      P3b the debt is discharged BEFORE `on_bar` (§7.12 condition 2).          2 failed
      P3c the retry RE-DERIVES the bar instead of re-publishing the seal.      3 failed
      P4  `poll_history` calls `_symbols.setdefault` again — F12 itself.       2 failed
      P5  the IBKR volume sentinel is not translated at the boundary.          2 failed
      P6  the TICK channel's measured figure serves the POLL channel too.      3 failed

    P3c is the one worth reading: besides T12 it reddened
    `test_the_adapter_derives_no_bar_from_ticks`, AMENDMENT 4's proof-by-absence gate, which
    counts `Bar(...)` constructions in the module by AST. A gate written for one property
    caught a violation of another, from a different arc, without being asked.

WHAT THIS SUITE CANNOT MEASURE, stated rather than left to be found:
  - Anything cross-THREAD or cross-PROCESS. `nics_risk_subsystem_spec_v1.3.md` §13:919-920
    objective 24 puts broker-datafeed in its own process; nothing here crosses that boundary.
  - Real socket behaviour. Everything is against a declared stand-in (debug.md failure mode
    #12: record the environment in the evidence). Nothing below is a claim about IBKR.
  - §5.2 FIT FOR PURPOSE in full. That needs the Limiter and capture.py, neither of which
    exists. Where a §5.2 observation is reachable anyway it is labelled and reported, not
    asserted as a verdict.
  - §5.6's full static sweep and §5.7's instrument audit. Both are tree-wide measurements with
    exactly one owner per debug.md §7.10, and this file's author is not it.
--------------------------------------------------------------------------------------
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# pylint suppressions for THIS FILE, each with its reason. Named codes only.
#
#   invalid-name
#       The logging fakes mirror ib_async's surface (reqMktData, cancelMktData,
#       reqMarketDataType). Renaming them to snake_case makes them stop standing
#       in for the thing they fake.
#   protected-access
#       The traversals read `ad._symbols[...]`, `ad._connected`, `ad._sink`,
#       `ad._requested_mode`. Those ARE the subject: a Tier-3 traversal of a
#       state-lifetime defect has to observe the state directly, and inferring it
#       from an output is the indirection CLAUDE.md directive 2 forbids.
#   missing-function-docstring / missing-class-docstring
#       Only on tiny local helpers and fake vendor methods; every test carries a
#       full docstring stating preconditions, expected end state and observable.
#   unused-argument
#       Fake vendor methods must accept the arguments the real ones take.
#   too-many-* / too-many-lines
#       A traversal suite's size IS its coverage, and each finding's reasoning is
#       load-bearing evidence for a triage decision the parent has to make.
#   duplicate-code
#       Setup preambles are deliberately identical across sequences so the
#       DIFFERENCE between two traversals is the sequence and nothing else.
#   disallowed-name
#       `bar` is the domain word for the thing this port publishes — the same
#       argument `broker_datafeed_ibkr.py` and `test_broker_datafeed.py` record.
#   use-implicit-booleaness-not-comparison
#       `== []` asserts the TYPE and the emptiness together; `not x` is also true
#       for None, which is what a mistyped observable returns.
# pylint: disable=invalid-name,protected-access,missing-function-docstring
# pylint: disable=missing-class-docstring,unused-argument,too-many-locals
# pylint: disable=too-many-statements,too-many-lines,duplicate-code,disallowed-name
# pylint: disable=use-implicit-booleaness-not-comparison
import ast
import asyncio
import inspect
import math
import pathlib
import time

import pytest  # pylint: disable=import-error
from broker_datafeed_ibkr import IBKRBrokerDatafeed
from broker_seam import (
    DATAFEED_ASYNC_VERBS,
    DATAFEED_PORT_VERBS,
    LAG_SAMPLE_FLOOR,
    LAG_WINDOW_S,
    Bar,
    BarSource,
    BrokerNotConnected,
    FeedChannel,
    FeedPollExhausted,
    FeedState,
    HollowBrokerDatafeed,
    LagAgreement,
    LagProvenance,
    LagWindowBound,
    MarketDataMode,
    RecordingFeedSink,
    check_structural_conformance,
)

# IMPORTED, never copied — Part C.9. See the module docstring.
from test_broker_datafeed import (  # pylint: disable=import-error
    FakeIBFeed,
    bar_row,
)

SYM = "MESU6"
OTHER = "NQZ6"

ADAPTER_SRC = (
    pathlib.Path(__file__).resolve().parents[1] / "broker" / "broker_datafeed_ibkr.py"
)

MEASURED: dict[str, object] = {}
"""§5.4 requires numbers to be RECORDED. They are recorded here and asserted on NOWHERE — a
measured figure written into an assertion is debug.md §7.4's third row (a literal describing the
current state of the world). The arc report reads this dict; the suite reads the relations."""


# --- §7.12 answer V2: the imported fake must still carry the surface we drive. -------
# Derived from what these traversals actually call, not a snapshot inventory. Adding a driver
# below without adding its dependency here is caught by an AttributeError at the call site
# rather than by a silent no-op, which is the direction that fails loudly.
_FIDELITY = (
    "bind",
    "connect",
    "disconnect",
    "reqMarketDataType",
    "reqMktData",
    "cancelMktData",
    "grant_map",
    "subscribed",
    "cancelled",
    "requested",
    "connected",
)
_MISSING = [name for name in _FIDELITY if not hasattr(FakeIBFeed(), name)]
if _MISSING:  # import-time non-vacuity guard, not a test — must fail COLLECTION
    raise RuntimeError(
        f"imported FakeIBFeed no longer carries {_MISSING} — these traversals would drive a "
        "fake that cannot represent the vendor surface they are written about"
    )
if "volume" not in bar_row(1.0) or "open" not in bar_row(1.0):
    raise RuntimeError(
        "imported bar_row no longer produces a full payload row — every seal/revision "
        "traversal below would be driving malformed rows and measuring the refusal instead"
    )


# ===========================================================================
# THE OBSERVABLES
# ===========================================================================


class EventLog:
    """An ORDERED log of sequence points, with the wall-free ordering these proofs need.

    debug.md §5.1's traversals are about ORDER, and an end-state assertion cannot express one.
    Every driver below writes `enter:<what>` / `exit:<what>` pairs here, so "did these two
    operations overlap" is answerable by reading the log rather than by trusting `gather`.

    NOT A TIMESTAMP LOG, deliberately: a wall clock introduces a timing window that goes stale
    (debug.md failure mode #6, and §7.4). Order is the invariant; duration is not.
    """

    def __init__(self) -> None:
        self.marks: list[str] = []

    def mark(self, what: str) -> None:
        self.marks.append(what)

    def overlapped(self, a: str, b: str) -> bool:
        """True iff `a` and `b` were both open at the same moment.

        COUNTED, NOT SET-MEMBERSHIP, and the difference is load-bearing: `a == b` is the single
        most important case here — two polls of the SAME symbol — and a set cannot express "two
        of them are open at once". A set-based first draft reported a serial run of one label as
        an overlap and would have turned T5's atomicity finding into its opposite.

        Spelled as an explicit scan rather than as a pattern match on the list, so the CONTROL
        can demonstrate it reports True for a genuine overlap and False for a serial run — the
        two verdicts that every atomicity claim below rests on.
        """
        depth: dict[str, int] = {}
        for m in self.marks:
            kind, _, what = m.partition(":")
            if kind == "enter":
                depth[what] = depth.get(what, 0) + 1
                if a == b:
                    if depth.get(a, 0) >= 2:
                        return True
                elif depth.get(a, 0) >= 1 and depth.get(b, 0) >= 1:
                    return True
            elif kind == "exit":
                depth[what] = max(0, depth.get(what, 0) - 1)
        return False

    def pairs(self) -> list[tuple[str, str]]:
        return [(m.partition(":")[0], m.partition(":")[2]) for m in self.marks]


def nonvac(condition: bool, what: str) -> None:
    """Non-vacuity assertion — distinct from the behavioural asserts on purpose.

    debug.md §7.3: prove the instrument's scope contains its subject BEFORE proving anything
    else. A failure here means the traversal never reached the state it claims to report on,
    which is CANNOT MEASURE (§7.9) and not a finding about the adapter.
    """
    assert condition, (
        f"NON-VACUITY FAILED (traversal never reached its subject): {what}"
    )


class LoggingFeed(FakeIBFeed):
    """`FakeIBFeed` that writes sequence points into an `EventLog`.

    EXTENDS the imported fake rather than replacing it (Part C.9): every measured ARC 013
    behaviour the parent carries — a grant that arrives as something else, a grant that never
    arrives at all — is inherited unchanged, and only the ordering marks are added.
    """

    def __init__(self, log: EventLog, grant_map=None):
        super().__init__(grant_map=grant_map)
        self.log = log

    def reqMktData(self, symbol):
        self.log.mark(f"enter:sub:{symbol}")
        super().reqMktData(symbol)
        self.log.mark(f"exit:sub:{symbol}")

    def cancelMktData(self, symbol):
        self.log.mark(f"enter:unsub:{symbol}")
        super().cancelMktData(symbol)
        self.log.mark(f"exit:unsub:{symbol}")


def logging_history(log: EventLog, rows_for):
    """A history source that brackets its own body with sequence points.

    `rows_for` is called with the symbol and returns the row list, so a traversal can vary the
    venue's answer per call (a revision) without varying the ordering instrumentation.
    """

    def source(symbol):
        log.mark(f"enter:poll:{symbol}")
        rows = rows_for(symbol)
        log.mark(f"exit:poll:{symbol}")
        return rows

    return source


async def new_ad(*, grant_map=None, history=None, log=None, connect=True, **kwargs):
    """The ONLY construction path — §7.12 answer V3.

    Returns the very objects it injected, so an assertion can never be reading a sink the
    adapter does not write to (debug.md §7.12's own eighth instance, ARC 016).
    """
    sink = RecordingFeedSink()
    fake = (
        LoggingFeed(log, grant_map=grant_map)
        if log is not None
        else FakeIBFeed(grant_map=grant_map)
    )
    ad = IBKRBrokerDatafeed(sink, ib=fake, history_source=history, **kwargs)
    fake.bind(ad)
    assert ad._sink is sink and ad._ib is fake
    if connect:
        await ad.connect()
    return ad, sink, fake


def saturate(ad, symbol, *, lag: float = 600.0, base_recv: float = 700.0) -> float:
    """Deliver exactly `LAG_SAMPLE_FLOOR` venue-stamped ticks and return the last `recv_ts`.

    ARC 023 (F17): the lag window declares ABSENCE below its floor rather than reporting a mean
    over too few samples, so a traversal that needs an OBSERVED reading has to reach the floor.
    THE COUNT IS DERIVED FROM `LAG_SAMPLE_FLOOR`, never typed — a literal here is `debug.md`
    §7.4's third row and it is exactly what went stale when the floor landed: six traversals
    drove one to four ticks and their own `nonvac()` guards caught every one of them, which is
    §7.3 working rather than a suite that had to be repaired.

    The packets are one second apart, so the whole set sits inside one `LAG_WINDOW_S` and the
    time bound is not what is being measured here."""
    last = base_recv
    for i in range(LAG_SAMPLE_FLOOR):
        last = base_recv + i
        ad._on_ib_tick(symbol, 1.0, 1.0, last - lag, recv_ts=last)
    return last


async def spin(times: int = 4) -> None:
    """Let the loop dispatch ready callbacks. No wall-clock dependency, so no timing window to
    go stale (debug.md failure mode #6)."""
    for _ in range(times):
        await asyncio.sleep(0)


# ===========================================================================
# THE GUARD EVERY CONCURRENCY CLAIM BELOW RESTS ON — §7.12 answer V1, and §7.6
# ===========================================================================


def test_guard_async_verbs_have_no_suspension_point() -> None:
    """PROOF BY ABSENCE (debug.md §7.6): not one D1.38 async verb can suspend.

    PRECONDITIONS: `DATAFEED_ASYNC_VERBS` names the five wire verbs; the adapter implements all
      five as `async def`.
    EXPECTED: every one of the five method bodies contains ZERO `await` expressions.
    OBSERVABLE: `ast.Await` nodes inside each verb's `AsyncFunctionDef`, read from the adapter's
      own source.

    THIS IS A GUARD, NOT A FINDING ASSERTION, and the distinction is load-bearing. Six
    traversals below claim ATOMICITY — that a cancel cannot land mid-poll, that two polls cannot
    interleave, that a disconnect cannot tear a poll in half. Every one of those claims is true
    ONLY because there is nowhere to suspend. The day `connect()` is bound to
    `ib_async.connectAsync` (which the adapter's own ASYNC SURFACE section records as owed), or
    the history source becomes an awaited vendor call, this guard goes RED and those traversals
    must be RE-READ, not re-run: their conclusions invert.

    SCOPE IS DERIVED, NEVER LISTED (§7.4 first row). The verb set comes from
    `DATAFEED_ASYNC_VERBS`, so a sixth async verb joins this guard by being declared. Proof by
    ABSENCE rather than by call site (§7.6): the module is scanned for the capability, not the
    places it might be used.
    """
    tree = ast.parse(ADAPTER_SRC.read_text(encoding="utf-8"))
    found = {
        node.name: [n for n in ast.walk(node) if isinstance(n, ast.Await)]
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef)
    }
    # NON-VACUITY FIRST (§7.3): the scan must actually contain its subject.
    nonvac(
        set(DATAFEED_ASYNC_VERBS) <= set(found),
        f"the AST found async defs {sorted(found)}, which does not cover the declared "
        f"partition {sorted(DATAFEED_ASYNC_VERBS)} — the guard cannot see its subject",
    )
    suspending = {v: len(found[v]) for v in DATAFEED_ASYNC_VERBS if found[v]}
    MEASURED["async_verbs_with_awaits"] = suspending
    assert suspending == {}, (
        f"{sorted(suspending)} now contain(s) an await. The async surface has acquired a real "
        "suspension point, so every ATOMICITY traversal in this file is now measuring a "
        "different module. Re-read them; do not re-run them."
    )


# ===========================================================================
# THE CONTROLS — debug.md §7.1, asserted STRUCTURALLY and BEHAVIOURALLY
# ===========================================================================


@pytest.mark.asyncio
async def test_control_interleave_detector_can_see_an_interleave() -> None:
    """CONTROL for §7.12 answer V1: `EventLog.overlapped` is not blind.

    PRECONDITIONS: two coroutines driven through the SAME recorder the traversals use — one
      pair that genuinely suspends between its enter and exit marks, one pair that does not.
    EXPECTED: the suspending pair is reported as OVERLAPPED; the serial pair is not.
    OBSERVABLE: `EventLog.overlapped()` over the two logs, and the raw mark order.

    WHY A CONTROL AND NOT A NOTE. Every atomicity claim below is of the form "these two
    operations did NOT overlap". That observation is indistinguishable from "the detector
    cannot report an overlap" unless the detector has been shown reporting one. Without this,
    six traversals are green over a dead instrument — debug.md failure mode #1 exactly.
    """
    # STRUCTURAL: the detector's verdict is computed from the mark stream and nothing else.
    src = inspect.getsource(EventLog.overlapped)
    assert "self.marks" in src and "time" not in src

    # BEHAVIOURAL, arm A — a genuine interleave.
    live = EventLog()

    async def suspending(name: str) -> None:
        live.mark(f"enter:{name}")
        await asyncio.sleep(0)
        live.mark(f"exit:{name}")

    await asyncio.gather(suspending("a"), suspending("b"))
    assert live.overlapped("a", "b"), (
        f"the detector MISSED a real interleave {live.marks} — every 'did not interleave' "
        "verdict in this file would be meaningless"
    )
    assert [k for k, _ in live.pairs()] == ["enter", "enter", "exit", "exit"]

    # BEHAVIOURAL, arm B — a serial run, over the same detector.
    serial = EventLog()

    async def atomic(name: str) -> None:
        serial.mark(f"enter:{name}")
        serial.mark(f"exit:{name}")

    await asyncio.gather(atomic("a"), atomic("b"))
    assert not serial.overlapped("a", "b")
    assert [k for k, _ in serial.pairs()] == ["enter", "exit", "enter", "exit"]

    # BEHAVIOURAL, arm C — the SAME LABEL twice, which is T5's and T9's actual question ("did
    # two polls of one symbol overlap"). A set-membership detector answers True for arm C's
    # serial case and would invert T5's finding; this is the arm that proves it does not.
    same_live, same_serial = EventLog(), EventLog()

    async def suspending_same() -> None:
        same_live.mark("enter:poll")
        await asyncio.sleep(0)
        same_live.mark("exit:poll")

    async def atomic_same() -> None:
        same_serial.mark("enter:poll")
        same_serial.mark("exit:poll")

    await asyncio.gather(suspending_same(), suspending_same())
    await asyncio.gather(atomic_same(), atomic_same())
    assert same_live.overlapped("poll", "poll")
    assert not same_serial.overlapped("poll", "poll")


@pytest.mark.asyncio
async def test_control_hollow_adapter_fails_the_traversal_observables() -> None:
    """CONTROL for §7.12 answer V8: the drivers really drive.

    PRECONDITIONS: `HollowBrokerDatafeed` — structurally conformant, behaviourally empty —
      driven through the same subscribe / poll / read sequence the traversals use.
    EXPECTED: it satisfies the whole roster (structural) AND produces none of the observables
      the traversals draw conclusions from (behavioural) — while returning a PLAUSIBLE,
      FULLY-POPULATED answer from the two sync reads, which is what makes it dangerous.
    OBSERVABLE: `check_structural_conformance` == [], an empty sink, and `granted_mode()` /
      `feed_lag()` returning REALTIME and a declared 0.0 that nothing measured.

    debug.md §7.12's vacuity table lists as instance 7 *an order sink passed into the datafeed
    port*, which survived precisely because no feed event was ever driven through it. Every sink
    here is driven, and this is the proof that driving them distinguishes anything.

    NOTE THE DIRECTION OF THE HOLLOW'S TWO SYNC READS, because a first draft of this control got
    it backwards and asserted UNKNOWN. `HollowBrokerDatafeed`'s own docstring says its
    `feed_lag` *"returns a FULLY-POPULATED, PLAUSIBLE object — declared 0.0, granted REALTIME —
    which is exactly the pre-ARC-021 stub's answer and exactly what AMENDMENT 3 forbids."* The
    control is therefore not "the hollow is empty everywhere"; it is that the hollow FABRICATES
    where the real adapter DECLARES, and the traversals distinguish the two.
    """
    hollow_sink = RecordingFeedSink()
    hollow = HollowBrokerDatafeed(hollow_sink)

    # STRUCTURAL: it passes the shape gate. That is the whole reason it is dangerous.
    assert check_structural_conformance(hollow, DATAFEED_PORT_VERBS) == []

    await hollow.connect()
    await hollow.subscribe(SYM)
    assert await hollow.poll_history(SYM) == 0
    await hollow.unsubscribe(SYM)

    # BEHAVIOURAL, half one: every event observable a traversal reads is EMPTY.
    assert hollow_sink.sequence == []
    assert hollow_sink.bars == []
    assert hollow_sink.feed_statuses == []

    # BEHAVIOURAL, half two: the two sync reads are plausible and fabricated.
    assert hollow.granted_mode() is MarketDataMode.REALTIME
    hollow_lag = hollow.feed_lag()
    assert hollow_lag.provenance is LagProvenance.VENDOR_DECLARED
    assert hollow_lag.declared_lag_s == 0.0
    assert hollow_lag.observed_n == 0

    # AND THE POINT: the real adapter, driven identically, differs on every one of them.
    ad, sink, _ = await new_ad(history=lambda s: [bar_row(100.0)])
    real_before_grant = ad.granted_mode()
    await ad.subscribe(SYM)
    assert await ad.poll_history(SYM) == 1
    assert sink.sequence != []
    assert sink.bars != []
    assert sink.feed_statuses != []
    assert (
        real_before_grant is MarketDataMode.UNKNOWN
    )  # the floor, not a plausible grant
    assert ad.granted_mode(SYM) is MarketDataMode.DELAYED
    assert ad.feed_lag(SYM).provenance is LagProvenance.PRIOR_ARC  # cited, not claimed


# ===========================================================================
# T1 — THE SAME OPERATION TWICE: subscribe
# ===========================================================================


@pytest.mark.asyncio
async def test_t1_subscribe_twice_destroys_a_grant_the_venue_will_not_resend() -> None:
    """SEQUENCE: subscribe(SYM) -> grant arrives -> subscribe(SYM) again, venue silent.

    PRECONDITIONS: a live session; the first subscribe receives a real grant callback (DELAYED).
      The second subscribe reaches a venue that sends NO second callback — which is IBKR's
      behaviour for a duplicate market-data request on a ticker id it already serves.
    EXPECTED END STATE: undetermined by any document. Observed: the grant is reset to the
      UNKNOWN sentinel and never moves again.
    OBSERVABLE: `granted_mode(SYM)` before and after, and `granted_mode_divergence(SYM)`.

    FINDING — SPEC GAP. `subscribe()` is not idempotent with respect to the grant: it writes the
    sentinel unconditionally (its own docstring: *"`granted_mode` is set to `UNKNOWN` here,
    BEFORE the request"*), so a repeat subscribe over a venue that does not re-grant converts a
    KNOWN grant into an unknown one permanently. The direction is FAIL-CLOSED — UNKNOWN is the
    pessimistic reading and a consumer gating on the grant refuses rather than trades — so this
    is degradation, not danger. It is still a finding, because at Stage 0 the delayed stream
    keeps flowing while the seam reports it ungranted, and `docs/CHECK-DEBT.md` D1.13's whole
    purpose is that the grant be readable.

    THE SECTION THAT WOULD HAVE TO SAY IT: `nics_risk_subsystem_spec_v1.3.md` §2A:87-89, the
    broker-datafeed command declaration. It declares `subscribe(symbol) / unsubscribe(symbol)`
    and takes NO view on repeat invocation — exactly the shape `docs/SPEC-AMENDMENTS.md`
    AMENDMENT 2 had to rule on for `flatten` on the order path. NO ANSWER IS INVENTED HERE: the
    observed behaviour is asserted and the disposition is the parent's.
    """
    ad, _, fake = await new_ad()
    await ad.subscribe(SYM)
    # NON-VACUITY (§7.12 V4): the grant must genuinely be held before the sequence destroys it.
    nonvac(
        ad.granted_mode(SYM) is MarketDataMode.DELAYED,
        f"first subscribe did not obtain a grant (got {ad.granted_mode(SYM)}) — the traversal "
        "would be observing a sentinel that was never displaced",
    )
    nonvac(fake.subscribed == [SYM], f"the venue was never asked: {fake.subscribed}")

    fake._adapter = None  # the venue sends no second grant callback
    await ad.subscribe(SYM)

    assert ad.granted_mode(SYM) is MarketDataMode.UNKNOWN
    assert "NO GRANT CALLBACK" in ad.granted_mode_divergence(SYM)
    # The venue WAS asked a second time, so this is not "the request never went out".
    assert fake.subscribed == [SYM, SYM]


@pytest.mark.asyncio
async def test_t1b_resubscribe_is_not_unsubscribe_then_subscribe() -> None:
    """SEQUENCE: subscribe -> tick -> subscribe   versus   subscribe -> tick -> unsubscribe ->
    subscribe. Two spellings of "start this subscription again".

    PRECONDITIONS: one venue-stamped tick on each adapter, so each carries exactly one lag
      sample before the second subscribe.
    EXPECTED END STATE: undetermined. Observed: the two paths end in DIFFERENT states — the
      re-subscribe keeps the lag samples and both receipt clocks and clears only the grant,
      while unsubscribe+subscribe clears everything.
    OBSERVABLE: `feed_lag(SYM).provenance` / `.observed_n`, and `last_tick_recv_ts(SYM)`.

    FINDING — INTERNAL CONTRADICTION (see the module docstring's declared label). The adapter
    states the rule itself, at `disconnect()`: *"Retaining a grant across a session boundary is
    the shape `docs/CHECK-DEBT.md` D1.24 records on the order path — state outliving the session
    it was true in."* `subscribe()` applies that rule to `granted_mode` and to nothing else, so
    after a re-subscribe `feed_lag(SYM)` reports `provenance=OBSERVED` — a measurement it
    attributes to the current subscription — out of samples collected under a grant the adapter
    has just declared it no longer knows. The FeedLag object then carries
    `granted_mode=UNKNOWN` beside `observed_lag_s` from a DELAYED grant, and those two fields
    are describing different subscriptions.

    NO REMEDY IS ASSERTED. Whether a re-subscribe should clear the samples, keep them, or make
    the two spellings equivalent is a decision, and `nics_risk_subsystem_spec_v1.3.md` §2A:87-89
    is silent on repeat invocation (the same gap T1 names). The traversal reports the asymmetry.
    """
    ad_a, _, fake_a = await new_ad()
    await ad_a.subscribe(SYM)
    last_a = saturate(ad_a, SYM)
    nonvac(
        ad_a.feed_lag(SYM).observed_n == LAG_SAMPLE_FLOOR,
        "no lag sample was collected, so neither path has anything to preserve or drop",
    )
    fake_a._adapter = None
    await ad_a.subscribe(SYM)

    ad_b, _, fake_b = await new_ad()
    await ad_b.subscribe(SYM)
    saturate(ad_b, SYM)
    nonvac(
        ad_b.feed_lag(SYM).observed_n == LAG_SAMPLE_FLOOR,
        "arm B collected no lag sample",
    )
    fake_b._adapter = None
    await ad_b.unsubscribe(SYM)
    await ad_b.subscribe(SYM)

    # Both arms end with the grant cleared — that half IS consistent.
    assert ad_a.granted_mode(SYM) is MarketDataMode.UNKNOWN
    assert ad_b.granted_mode(SYM) is MarketDataMode.UNKNOWN

    # And the observation history does not: one arm kept it, the other did not.
    a_lag, b_lag = ad_a.feed_lag(SYM), ad_b.feed_lag(SYM)
    assert (
        a_lag.provenance is LagProvenance.OBSERVED
        and a_lag.observed_n == LAG_SAMPLE_FLOOR
    )
    assert b_lag.provenance is LagProvenance.PRIOR_ARC and b_lag.observed_n == 0
    assert ad_a.last_tick_recv_ts(SYM) == last_a
    assert ad_b.last_tick_recv_ts(SYM) is None
    # THE CONTRADICTION, stated as a relation rather than as two snapshots: the surviving
    # measurement is reported alongside a grant the adapter says it does not know.
    assert a_lag.granted_mode is MarketDataMode.UNKNOWN
    assert a_lag.observed_lag_s == 600.0


# ===========================================================================
# T2 — OPERATIONS INTERLEAVED: subscribe / unsubscribe over one symbol
# ===========================================================================


@pytest.mark.asyncio
async def test_t2_subscribe_and_unsubscribe_cannot_interleave_and_last_writer_wins() -> (
    None
):
    """SEQUENCE: `asyncio.gather(subscribe(SYM), unsubscribe(SYM))` — overlap, one symbol.

    PRECONDITIONS: a live session and an EventLog wired through the fake's `reqMktData` /
      `cancelMktData`, so the venue calls bracket themselves.
    EXPECTED END STATE: the two verbs run to completion in submission order, without overlap,
      and the LAST one decides — here `unsubscribe` runs second and the symbol is forgotten.
    OBSERVABLE: `EventLog.pairs()` (the ordering), plus `_symbols` membership and the fake's
      `subscribed` / `cancelled` lists.

    FINDING — WORKING AS INTENDED, BUT ONLY BY ACCIDENT, and that is the report. The ordering
    guarantee here is not designed: it exists because neither verb contains an `await` (see
    `test_guard_async_verbs_have_no_suspension_point`). D1.38 promoted these verbs to
    coroutines specifically so a vendor round-trip could live inside them; the moment one does,
    this traversal's log will show `enter:sub / enter:unsub / exit:...` and the last-writer-wins
    property disappears with no other change to the module. The atomicity is therefore a
    property of TODAY's bodies, not of the contract, and nothing in `broker_seam.py` records
    that a consumer may rely on it.
    """
    log = EventLog()
    ad, _, fake = await new_ad(log=log)
    await ad.subscribe(SYM)
    nonvac(
        SYM in ad._symbols,
        "the symbol was never subscribed, so there is no overlap to run",
    )
    log.marks.clear()

    await asyncio.gather(ad.subscribe(SYM), ad.unsubscribe(SYM))

    # NON-VACUITY: both venue calls must have happened, or the "ordering" is of one event.
    nonvac(
        fake.subscribed == [SYM, SYM] and fake.cancelled == [SYM],
        f"the gather did not drive both verbs: subscribed={fake.subscribed} "
        f"cancelled={fake.cancelled}",
    )
    # ORDERING, asserted — not the end state alone (the brief's B2 rule).
    assert log.pairs() == [
        ("enter", f"sub:{SYM}"),
        ("exit", f"sub:{SYM}"),
        ("enter", f"unsub:{SYM}"),
        ("exit", f"unsub:{SYM}"),
    ]
    assert not log.overlapped(f"sub:{SYM}", f"unsub:{SYM}")
    # LAST WRITER WINS: unsubscribe ran second, so the symbol is gone.
    assert SYM not in ad._symbols
    assert ad.granted_mode(SYM) is MarketDataMode.UNKNOWN


# ===========================================================================
# T3 — THE SILENT-NO-OP CLASS: unsubscribe for a symbol never subscribed
# ===========================================================================


@pytest.mark.asyncio
async def test_t3_unsubscribe_of_an_unheld_symbol_is_indistinguishable_from_a_real_one() -> (
    None
):
    """SEQUENCE: unsubscribe(SYM) with no subscription at all, then subscribe + unsubscribe.

    PRECONDITIONS: a live session. Arm A has never subscribed; arm B holds a live subscription.
    EXPECTED END STATE: both return None, emit nothing on the sink, and leave `_symbols` empty.
    OBSERVABLE: the return value, the sink's `sequence` delta, and the fake's `cancelled` list —
      the ONLY thing that differs, and it lives on the VENDOR fake, not at the seam.

    FINDING — WORKING AS INTENDED, BUT SURPRISING, with a named precedent against it. The
    adapter's docstring declares this: *"Idempotent: unsubscribing an unheld symbol is not an
    error, because `nics_risk_subsystem_spec_v1.3.md` §2A:89 declares no precondition on it."*
    The surprise is that the no-op is UNOBSERVABLE ABOVE THE SEAM. The order library reached the
    opposite conclusion for the same shape and built `FlattenAttempt` with an explicit
    `is_silent_no_op()` — a RETAINED observable — precisely so a caller could tell "I cancelled
    something" from "there was nothing to cancel". This port has `poll_attempts()` for the poll
    path and nothing for the subscription path.

    INVARIANT 3 IS NOT A COUNTER-ARGUMENT AND IS ADDRESSED HERE SO IT IS NOT RAISED AS ONE:
    §2A:105-106 forbids a shared OBJECT between the two libraries, not a shared DISCIPLINE. The
    recommendation is an independently-written attempt record, not an import.

    NOT A SPEC GAP: §2A:89 genuinely declares no precondition, so the adapter is compliant. The
    gap is in OBSERVABILITY, which §2A does not legislate for either port — the order side
    closed it by decision (`docs/CHECK-DEBT.md` D1.28), not by spec.
    """
    ad, sink, fake = await new_ad()
    nonvac(
        ad._connected, "no session: the traversal would be measuring the refusal path"
    )

    before = list(sink.sequence)
    assert await ad.unsubscribe(SYM) is None  # arm A: never subscribed
    assert sink.sequence == before
    assert ad._symbols == {}
    assert fake.cancelled == []

    await ad.subscribe(SYM)
    nonvac(SYM in ad._symbols, "arm B never established a subscription to cancel")
    before = list(sink.sequence)
    assert await ad.unsubscribe(SYM) is None  # arm B: a real cancellation
    assert sink.sequence == before
    assert ad._symbols == {}

    # THE FINDING, as a relation: the two arms differ ONLY in a vendor-side record. Nothing the
    # seam publishes or retains distinguishes them.
    assert fake.cancelled == [SYM]
    assert not hasattr(ad, "unsubscribe_attempts")


# ===========================================================================
# T4 — A CALLER THAT ABANDONS MIDWAY: cancelling a poll
# ===========================================================================


@pytest.mark.asyncio
async def test_t4_a_cancelled_poll_is_never_torn_because_it_cannot_be_cancelled_midway() -> (
    None
):
    """SEQUENCE: `create_task(poll_history)` then `cancel()` — before the first step, and after.

    PRECONDITIONS: a live session, a subscribed symbol, and a history source that returns one
      row and brackets itself in the EventLog.
    EXPECTED END STATE: exactly two outcomes exist and no third. Either the poll never started
      (no attempt recorded, no bar sealed) or it completed whole (attempt recorded AND its rows
      sealed). A partially-ingested poll is unreachable.
    OBSERVABLE: `task.cancelled()`, `poll_attempts()`, `sealed_bars()`, and the EventLog.

    THE INVARIANT ASSERTED, not the snapshot (§7.4): *every attempt recorded `ok=True` has its
    rows sealed*. That relation stays true under a refactor that changes when the attempt is
    logged; a literal "0 attempts" would not.

    FINDING — WORKING AS INTENDED, BY ABSENCE. `poll_history` has no suspension point, so a
    cancel can only land in the gaps between the caller's awaits. `Task.cancel()` issued after
    one loop step returns FALSE — the task is already done. That is a real safety property
    today and it is not a designed one: it is the guard test's finding restated at the level a
    caller experiences. It should be recorded as a PRECONDITION of binding `connectAsync` or an
    async history source, because at that moment `_ingest_history` — which seals, publishes and
    returns without a checkpoint — becomes interruptible between the seal and the publish, and
    T12 below shows exactly what that costs.
    """
    log = EventLog()
    ad, sink, _ = await new_ad(
        log=log, history=logging_history(log, lambda s: [bar_row(100.0)])
    )
    await ad.subscribe(SYM)
    log.marks.clear()

    # ARM A — abandoned before the loop ever ran it.
    early = asyncio.create_task(ad.poll_history(SYM))
    early.cancel()
    with pytest.raises(asyncio.CancelledError):
        await early
    nonvac(
        early.cancelled(),
        "the task was not actually cancelled — arm A measured nothing",
    )
    assert ad.poll_attempts() == ()
    assert ad.sealed_bars() == ()
    assert log.marks == []

    # ARM B — abandoned after the loop had a chance to run it.
    late = asyncio.create_task(ad.poll_history(SYM))
    await asyncio.sleep(0)
    delivered = late.cancel()
    assert await late == 1
    # NON-VACUITY: the cancel really was issued at a point where it could have landed.
    nonvac(
        delivered is False and late.done(),
        f"cancel() returned {delivered!r} with done={late.done()} — arm B did not reach the "
        "state it reports on",
    )
    assert log.pairs() == [("enter", f"poll:{SYM}"), ("exit", f"poll:{SYM}")]

    # THE INVARIANT: no attempt is recorded whose rows are not sealed. Torn state is unreachable.
    for attempt in ad.poll_attempts():
        if attempt.ok:
            assert len(ad.sealed_bars()) >= attempt.rows
    assert len(sink.bars) == len(ad.sealed_bars()) == 1


# ===========================================================================
# T5 — TWO OVERLAPPING POLLS FOR ONE SYMBOL (ARC 020's D1.26 shape)
# ===========================================================================


@pytest.mark.asyncio
async def test_t5_two_overlapping_polls_serialise_and_seal_once_per_key() -> None:
    """SEQUENCE: `asyncio.gather(poll_history(SYM), poll_history(SYM))` over one symbol.

    PRECONDITIONS: a live session, a subscribed symbol, a history source returning the SAME two
      rows to both calls and bracketing itself in the EventLog.
    EXPECTED END STATE: two venue round-trips, two attempts recorded, and exactly ONE seal per
      key — the second poll's rows are recognised as already sealed and dropped, not re-sealed
      and not published as revisions.
    OBSERVABLE: the EventLog ordering, `poll_attempts()`, `sealed_bars()` and the sink's `bars`
      / `bar_revisions`.

    NON-VACUITY IS THE POINT OF THIS ONE. The first draft asserted one-seal-per-key and passed —
    over two polls that had never overlapped. `EventLog.overlapped()` is asserted explicitly so
    the traversal states what it actually measured: the two calls ran STRICTLY SERIALLY, and the
    seal store's idempotence was therefore proved against repetition rather than against
    concurrency. Both are worth proving; conflating them is not.

    ENCODING 2 — a derived relation that holds: one seal per `seal_key`, `seal_seq` strictly
    increasing, and no revision for identical rows.
    """
    log = EventLog()
    rows = [bar_row(100.0), bar_row(160.0)]
    ad, sink, _ = await new_ad(
        log=log, history=logging_history(log, lambda s: list(rows))
    )
    await ad.subscribe(SYM)
    log.marks.clear()

    results = await asyncio.gather(ad.poll_history(SYM), ad.poll_history(SYM))

    nonvac(
        len(ad.poll_attempts()) == 2,
        f"only {len(ad.poll_attempts())} venue attempt(s) — the second poll never ran",
    )
    # WHAT ACTUALLY HAPPENED, asserted rather than assumed: no overlap.
    assert log.pairs() == [
        ("enter", f"poll:{SYM}"),
        ("exit", f"poll:{SYM}"),
        ("enter", f"poll:{SYM}"),
        ("exit", f"poll:{SYM}"),
    ]
    assert not log.overlapped(f"poll:{SYM}", f"poll:{SYM}")

    # THE DERIVED RELATIONS.
    assert results == [2, 2]  # both report what the VENUE returned...
    keys = [b.seal_key for b in ad.sealed_bars()]
    assert len(keys) == len(set(keys)) == 2  # ...and only one seal exists per key
    assert [b.seal_seq for b in ad.sealed_bars()] == sorted(
        b.seal_seq for b in ad.sealed_bars()
    )
    assert len(sink.bars) == 2
    assert sink.bar_revisions == []

    # SECONDARY FINDING — WORKING AS INTENDED, SURPRISING: the return value is the venue's row
    # count, documented as such, and it is NOT the number of bars published. A caller summing
    # returns across polls over-counts its own history by exactly the re-poll overlap, and the
    # seam offers no published-count observable to correct it.
    assert sum(results) == 4 and len(sink.bars) == 2


# ===========================================================================
# T6 — SEAL VERSUS STREAM, BOTH WRITING
# ===========================================================================


@pytest.mark.asyncio
async def test_t6_a_revision_arrives_while_the_stream_is_live() -> None:
    """SEQUENCE: subscribe -> poll (seal) -> tick -> re-poll returning a REVISED bar -> tick.

    PRECONDITIONS: a live session and a subscribed symbol; the history source returns a
      different `close` on the second call, so the re-poll genuinely contradicts the seal.
    EXPECTED END STATE: the sealed bar is UNCHANGED, one `on_bar_revision` names the differing
      field, and the tick stream's clocks are untouched by the poll path.
    OBSERVABLE: the sink's cross-stream `sequence`, `sealed_bar(...)`, `bar_revisions()`, and
      the two receipt clocks read per writer.

    ENCODING 2 — the derived relations, under interleaving of the two writers:
      (a) for the revised key, `on_bar` precedes `on_bar_revision` in the cross-stream sequence;
      (b) the sealed object is byte-for-byte what it was before the re-poll;
      (c) `last_tick_recv_ts` is written only by the tick path and `last_poll_recv_ts` only by
          the poll path — the ARC 020 A8 per-writer rule, asserted here under INTERLEAVING
          rather than in isolation, which is the part `test_broker_datafeed.py` cannot state.

    NON-VACUITY (§7.12 V5): the two payloads are asserted to differ before any revision claim.
    A traversal whose re-poll returns identical rows proves nothing, and is the exact shape
    `BarRevision`'s own docstring warns about.
    """
    call = {"n": 0}

    def history(symbol):
        call["n"] += 1
        return [bar_row(100.0) if call["n"] == 1 else bar_row(100.0, c=99.0)]

    ad, sink, _ = await new_ad(history=history)
    await ad.subscribe(SYM)

    await ad.poll_history(SYM)
    sealed_before = ad.sealed_bar(SYM, 100.0, 60.0)
    nonvac(
        sealed_before is not None, "nothing was sealed, so there is nothing to revise"
    )
    poll_clock_1 = ad.last_poll_recv_ts(SYM)

    ad._on_ib_tick(SYM, 1.0, 1.0, 100.0, recv_ts=700.0)
    tick_clock = ad.last_tick_recv_ts(SYM)
    nonvac(tick_clock == 700.0, "the tick path never wrote its clock")

    await ad.poll_history(SYM)
    ad._on_ib_tick(SYM, 2.0, 1.0, 101.0, recv_ts=701.0)

    nonvac(
        len(sink.bar_revisions) == 1,
        f"the re-poll produced {len(sink.bar_revisions)} revisions — the two payloads did not "
        "genuinely differ, so this traversal measured an identical re-poll",
    )

    # (a) ORDERING across the two streams.
    seq = sink.sequence
    assert seq.index("on_bar") < seq.index("on_bar_revision")
    assert seq == ["on_feed_status", "on_bar", "on_tick", "on_bar_revision", "on_tick"]

    # (b) THE SEAL IS UNCHANGED — the object itself, not a copy of its fields.
    assert ad.sealed_bar(SYM, 100.0, 60.0) is sealed_before
    revision = sink.bar_revisions[0]
    assert revision.sealed is sealed_before
    assert revision.differing_fields == ("close",)
    assert revision.revised_payload != sealed_before.payload()

    # (c) PER-WRITER CLOCKS, under interleaving.
    assert ad.last_tick_recv_ts(SYM) == 701.0
    assert ad.last_poll_recv_ts(SYM) != poll_clock_1
    assert ad.last_poll_recv_ts(SYM) != 701.0


# ===========================================================================
# T7 — SESSION DROP AND RECONNECT WITH SUBSCRIPTIONS OUTSTANDING
# ===========================================================================


@pytest.mark.asyncio
async def test_t7_subscriptions_are_not_re_established_and_their_state_outlives_the_session() -> (
    None
):
    """SEQUENCE: subscribe -> tick -> disconnect -> connect -> read everything -> unsubscribe.

    PRECONDITIONS: a live session with one subscribed symbol carrying one lag sample.
    EXPECTED END STATE: undetermined by any document. Observed: the grant is cleared (declared,
      correct) while the symbol ENTRY, its lag samples and both receipt clocks survive the
      session boundary intact; no re-subscription is issued to the venue; and a later
      `unsubscribe` sends `cancelMktData` for a subscription the venue no longer holds.
    OBSERVABLE: `_symbols` membership, `feed_lag(SYM)`, the fake's `subscribed` / `cancelled`
      lists across the boundary.

    FINDING — INTERNAL CONTRADICTION, and it is the same sentence T1b cites, applied to the
    verb that wrote it. `disconnect()` clears `granted_mode` and says why: *"the session that
    granted this is gone, so the grant is gone with it. Retaining a grant across a session
    boundary is the shape `docs/CHECK-DEBT.md` D1.24 records on the order path — state outliving
    the session it was true in."* The lag samples and both receipt clocks are state of exactly
    that kind and are retained, so after a reconnect `feed_lag(SYM)` reports
    `provenance=OBSERVED` about a session that no longer exists. D1.24's order-path repair was
    to CLEAR per-order state at every session boundary; this port clears one field of five.

    SECOND HALF, and the one with a venue consequence: the adapter never re-subscribes. The
    symbol is still in `_symbols`, so `_on_ib_tick` accepts packets for it, `evaluate_freshness`
    includes it, and `unsubscribe` believes it holds it and issues a real `cancelMktData` for a
    subscription IBKR dropped at the socket. Whether re-subscription is the adapter's job is
    genuinely undetermined — see the SPEC GAP below — but the state saying it still holds one is
    not undetermined; it is wrong by the module's own rule.

    THE SECTION THAT WOULD HAVE TO SAY IT (for the re-subscription half only):
    `nics_risk_subsystem_spec_v1.3.md` §2A:87-89 declares `connect/disconnect` and
    `subscribe/unsubscribe` and says nothing about what a reconnect owes an outstanding
    subscription. `§4 "Boot / known-state discipline"` governs the ORDER path's session
    re-establishment and has no datafeed counterpart — the same absence
    `docs/SPEC-AMENDMENTS.md` AMENDMENT 1 had to be issued for one library over.
    """
    ad, _, fake = await new_ad()
    await ad.subscribe(SYM)
    last_recv = saturate(ad, SYM)
    nonvac(
        ad.feed_lag(SYM).observed_n == LAG_SAMPLE_FLOOR
        and ad.granted_mode(SYM) is MarketDataMode.DELAYED,
        "the traversal did not establish a granted subscription with an observation to outlive "
        "it — there is no session boundary to cross",
    )
    subscribed_before = list(fake.subscribed)

    await ad.disconnect()
    assert (
        ad.granted_mode(SYM) is MarketDataMode.UNKNOWN
    )  # the declared clearing, honoured
    assert ad.feed_state() is FeedState.DOWN

    await ad.connect()
    assert ad._connected

    # HALF ONE — state outlived the session it was true in.
    assert SYM in ad._symbols
    after = ad.feed_lag(SYM)
    assert after.provenance is LagProvenance.OBSERVED
    assert after.observed_lag_s == 600.0 and after.observed_n == LAG_SAMPLE_FLOOR
    assert ad.last_tick_recv_ts(SYM) == last_recv

    # HALF TWO — nothing was re-subscribed, and the venue is asked to cancel it anyway.
    assert fake.subscribed == subscribed_before
    await ad.unsubscribe(SYM)
    assert fake.cancelled == [SYM]


@pytest.mark.asyncio
async def test_t7b_a_tick_arriving_after_disconnect_is_published_over_a_dead_session() -> (
    None
):
    """SEQUENCE: subscribe -> disconnect -> the venue delivers one more packet.

    PRECONDITIONS: a live subscription, then a clean `disconnect()` — `_connected` is False and
      the last published feed state is DOWN.
    EXPECTED END STATE: undetermined. Observed: `on_tick` is emitted to the sink, both clocks
      are written and a lag sample is appended, while `feed_state()` reads DOWN.
    OBSERVABLE: the sink's `ticks` and `sequence`, `feed_state()`, `feed_lag(SYM).observed_n`.

    FINDING — CODE DEFECT (fail-open on a dead session). Every command verb that touches state
    calls `_require_session`; the vendor CALLBACKS call nothing. A queued `ib_async` event
    delivered after `disconnect()` — which is the ordinary shape of an event-driven client
    shutting down — is therefore accepted, published to the consumer, and folded into the lag
    statistics of a session that has ended. The order library states the property this one
    lacks: `test_broker_tier3.py`'s T11 asserts *no publish over a dead session AND a publish
    over a live one*. INVARIANT 3 is not violated by holding both to the same DISCIPLINE; only
    by sharing the code.

    RECOMMENDED DISPOSITION is the parent's, and the two candidates differ in kind: refuse the
    packet (fail closed, loses a late-but-real observation) or admit it with a declared marker
    (`SessionState.UP_DATA_LOSS` is the precedent one library over). Nothing is asserted about
    which; the traversal asserts what happens today.
    """
    ad, sink, _ = await new_ad()
    await ad.subscribe(SYM)
    last_recv = saturate(ad, SYM)
    nonvac(
        len(sink.ticks) == LAG_SAMPLE_FLOOR,
        "the live-session arm never delivered a tick to compare with",
    )

    await ad.disconnect()
    nonvac(
        not ad._connected and ad.feed_state() is FeedState.DOWN,
        "the session was not actually torn down — the traversal is still on a live session",
    )

    before = len(sink.ticks)
    # DELIVERED INSIDE THE SAME LAG WINDOW as the live-session packets (ARC 023): the finding
    # is about a DEAD SESSION, and a packet placed a window-width later would be excluded by
    # the time bound instead, which measures something else.
    dead_recv = last_recv + 1.0
    ad._on_ib_tick(SYM, 2.0, 1.0, dead_recv - 600.0, recv_ts=dead_recv)

    # THE FINDING: a full publication over a session the adapter has declared DOWN.
    assert len(sink.ticks) == before + 1
    assert sink.ticks[-1] == (SYM, 2.0, 1.0, dead_recv - 600.0, dead_recv)
    assert sink.sequence[-1] == "on_tick"
    assert ad.feed_state() is FeedState.DOWN
    # AND IT MOVED THE STATISTICS: the window grew by exactly the dead-session packet.
    assert ad.feed_lag(SYM).observed_n == LAG_SAMPLE_FLOOR + 1
    assert ad.last_tick_recv_ts(SYM) == dead_recv


# ===========================================================================
# T8 — A GRANT THAT CHANGES (D1.13's live shape)
# ===========================================================================


@pytest.mark.asyncio
async def test_t8_a_grant_that_changes_is_state_only_and_is_never_published() -> None:
    """SEQUENCE: subscribe (granted DELAYED) -> tick -> the venue re-grants a DIFFERENT mode.

    PRECONDITIONS: a live subscription whose grant callback genuinely arrived and moved the
      sentinel off UNKNOWN.
    EXPECTED END STATE: undetermined. Observed: `granted_mode(SYM)` moves to the new mode, the
      previous grant is overwritten with no record that it changed, and NOTHING is emitted on
      any sink event.
    OBSERVABLE: `granted_mode(SYM)` before/after, `granted_mode_divergence(SYM)`, and the sink's
      `sequence` delta across the re-grant.

    FINDING — SPEC GAP. `docs/CHECK-DEBT.md` D1.13's owed behaviour is *"assert the granted
    marketDataType and FAIL on a silent downgrade"*, and the adapter delivers the first half:
    the grant is sentinelled, the divergence is a readable value rather than a log line. What it
    has no way to do is TELL ANYBODY. `nics_risk_subsystem_spec_v1.3.md` §2A:86-92 is a
    push/callback model — its own words, *"no polling on the hot path"* — and gives the datafeed
    exactly two events. `on_feed_status` carries a `FeedState`, whose three members are UP /
    DOWN / STALE; a mid-session mode change is none of those. So the one fact D1.13 exists to
    surface is reachable only by a consumer POLLING `granted_mode()` on a port declared push.

    THE SECTION THAT WOULD HAVE TO SAY IT: `nics_risk_subsystem_spec_v1.3.md` §2A:90-92, the
    broker-datafeed EVENT declaration — the same two lines `docs/SPEC-AMENDMENTS.md`
    AMENDMENT 4 had to scope for `on_bar`. NO ANSWER IS INVENTED: whether this is a third
    `FeedState` member, a third event, or a documented pull is a contract decision.

    SECONDARY OBSERVATION, recorded because it is the more dangerous direction: the callback
    accepts an UPGRADE as readily as a downgrade. A venue that sends `marketDataType=1` on a
    Stage 0 account moves `granted_mode` to REALTIME, and `granted_mode_divergence` reports it
    as a divergence from the request — but nothing refuses it, and every measured fact in
    `IB_MARKETDATA_EVIDENCE` says this account cannot be granted real-time.
    """
    ad, sink, _ = await new_ad()
    await ad.subscribe(SYM)
    nonvac(
        ad.granted_mode(SYM) is MarketDataMode.DELAYED,
        "no grant ever arrived, so there is no grant to change",
    )
    assert ad.granted_mode_divergence(SYM) == ""
    before = list(sink.sequence)

    # The venue re-grants, mid-session, with no re-subscribe — the D1.13 live shape.
    ad._on_ib_market_data_type(SYM, MarketDataMode.DELAYED_FROZEN.value)

    assert ad.granted_mode(SYM) is MarketDataMode.DELAYED_FROZEN
    assert "SILENT DOWNGRADE" in ad.granted_mode_divergence(SYM)
    # THE FINDING: the seam published nothing. The change is visible only to a caller that asks.
    assert sink.sequence == before

    # THE MORE DANGEROUS DIRECTION, on a fresh adapter so the two are not confounded.
    ad2, sink2, _ = await new_ad()
    await ad2.subscribe(SYM)
    before2 = list(sink2.sequence)
    ad2._on_ib_market_data_type(SYM, MarketDataMode.REALTIME.value)
    assert ad2.granted_mode(SYM) is MarketDataMode.REALTIME
    assert sink2.sequence == before2


# ===========================================================================
# T9 — TEARDOWN WITH WORK OUTSTANDING
# ===========================================================================


@pytest.mark.asyncio
async def test_t9_disconnect_racing_a_poll_cannot_tear_it_and_order_decides_everything() -> (
    None
):
    """SEQUENCE: `asyncio.gather(poll_history(SYM), disconnect())`, then the reverse order.

    PRECONDITIONS: a live session, a subscribed symbol, a bracketing history source.
    EXPECTED END STATE: the two verbs serialise. Submitted poll-first, the poll completes whole
      and the session is then torn down. Submitted disconnect-first, the poll finds no session
      and raises `BrokerNotConnected` — with nothing half-done in either case.
    OBSERVABLE: the EventLog, `sealed_bars()`, `_connected`, and the raised type.

    ENCODING 2 for the relation that holds — *a poll is all-or-nothing across a teardown* — and
    a WORKING-AS-INTENDED-BY-ACCIDENT finding for why: the same absent suspension point. This
    traversal is the one whose conclusion inverts most sharply when `connectAsync` lands, because
    `_ingest_history` seals a bar and THEN publishes it, and T12 measures what an interruption
    between those two steps costs. Recorded as a precondition on that change.

    NOTE ON THE REFUSAL ARM: `BrokerNotConnected` is asserted by TYPE, never by message
    (§7.4's fourth row — a refactor changes the wording).
    """
    log = EventLog()
    ad, sink, _ = await new_ad(
        log=log, history=logging_history(log, lambda s: [bar_row(100.0)])
    )
    await ad.subscribe(SYM)
    log.marks.clear()

    # ARM A — poll submitted first.
    await asyncio.gather(ad.poll_history(SYM), ad.disconnect())
    nonvac(
        log.marks != [],
        "the poll never reached the venue, so nothing raced the teardown",
    )
    assert log.pairs()[:2] == [("enter", f"poll:{SYM}"), ("exit", f"poll:{SYM}")]
    assert not ad._connected
    assert len(ad.sealed_bars()) == 1 and len(sink.bars) == 1

    # ARM B — teardown first, from a fresh session, so the two arms are independent.
    ad2, sink2, _ = await new_ad(history=lambda s: [bar_row(100.0)])
    await ad2.subscribe(SYM)
    with pytest.raises(BrokerNotConnected):
        await asyncio.gather(ad2.disconnect(), ad2.poll_history(SYM))
    assert ad2.sealed_bars() == ()
    assert sink2.bars == []
    assert ad2.poll_attempts() == ()


# ===========================================================================
# T10 — A RETAINED OBSERVABLE READ OVER A SESSION THAT MOVED
# ===========================================================================


@pytest.mark.asyncio
async def test_t10_feed_lag_read_across_a_reconnect_reports_a_dead_session_as_observed() -> (
    None
):
    """SEQUENCE: subscribe -> ticks -> read feed_lag -> disconnect -> read -> connect -> read.

    PRECONDITIONS: two venue-stamped ticks whose lag matches the banked ARC 013 figure closely
      enough that `agreement` reads AGREES, so the traversal starts from a healthy reading.
    EXPECTED END STATE: undetermined. Observed: the reading is IDENTICAL at all three points.
      `feed_lag()` is a sync verb over retained state and takes no view on whether the session
      that produced the state still exists.
    OBSERVABLE: `provenance`, `observed_lag_s`, `observed_n`, `agreement` at the three reads.

    FINDING — INTERNAL CONTRADICTION, the third face of T1b's and T7's. `LagProvenance.OBSERVED`
    is documented as *"Measured by this adapter, IN THIS SESSION, from packets it received"* —
    emphasis in the original enum. After a reconnect the session is a different one, and the
    provenance still says OBSERVED. The enum was built precisely to stop a figure from a
    different moment reading as a figure from this one: `PRIOR_ARC` exists for that, and its
    docstring says *"evidence about the venue at a past moment, not about this session"*. A
    session boundary is exactly that transition, and nothing moves the provenance across it.

    WHY THIS IS NOT MERELY COSMETIC: `evaluate_freshness` calls `feed_lag(sym)` and subtracts
    `effective_lag_s` from the data age. After a reconnect it subtracts a lag measured on the
    previous session — under a grant the adapter has just declared it no longer knows — from a
    staleness computation whose verdict `nics_risk_subsystem_spec_v1.3.md` §6.4:373-374 turns
    into *halt new entries AND flatten open*.

    NO REMEDY ASSERTED. Whether the samples should be dropped, re-provenanced, or windowed is a
    decision that belongs with T16's finding about the same list.
    """
    ad, _, _ = await new_ad()
    await ad.subscribe(SYM)
    saturate(ad, SYM, lag=600.3)

    live = ad.feed_lag(SYM)
    nonvac(
        live.provenance is LagProvenance.OBSERVED
        and live.agreement is LagAgreement.AGREES,
        f"the traversal did not start from a healthy observed reading: {live.provenance} / "
        f"{live.agreement}",
    )

    await ad.disconnect()
    down = ad.feed_lag(SYM)
    await ad.connect()
    up = ad.feed_lag(SYM)

    def reading(fl):
        return (fl.provenance, fl.observed_lag_s, fl.observed_n, fl.agreement)

    # THE INVARIANT ASSERTED IS THE SAMENESS, not the value: the reading does not depend on the
    # session at all, which is the finding.
    assert reading(live) == reading(down) == reading(up)
    assert up.provenance is LagProvenance.OBSERVED
    # And the one field that DID move is the grant — so the object now mixes the two.
    assert live.granted_mode is MarketDataMode.DELAYED
    assert up.granted_mode is MarketDataMode.UNKNOWN


# ===========================================================================
# T11 — A CROSS-VERB SIDE EFFECT: polling manufactures a subscription
#        ADDED. Reason: the ten sequences are all within one pathway. This is the first
#        place two pathways write the same structure, and `_SymbolFeedState`'s docstring
#        says that structure means "everything this adapter knows about ONE subscription".
# ===========================================================================


@pytest.mark.asyncio
async def test_t11_polling_an_unsubscribed_symbol_manufactures_no_subscription_state() -> (
    None
):
    """SEQUENCE: subscribe(SYM) -> read the adapter-wide grant -> poll_history(OTHER) -> read
    it again -> unsubscribe(OTHER).

    PRECONDITIONS: one genuinely subscribed symbol holding a real grant, and a second symbol
      that has NEVER been subscribed.
    EXPECTED END STATE (determined by the repair below): the poll is RECORDED and no
      subscription is created — `OTHER` is in `polled_symbols()` and not in `_symbols`, the
      adapter-wide grant is unmoved, and `unsubscribe(OTHER)` puts nothing on the wire.
    OBSERVABLE: `granted_mode()` before/after, `_symbols` and `polled_symbols()` membership,
      and the fake's `cancelled` list.

    FINDING — CODE DEFECT, **CLOSED IN ARC 023 (F12)**, and this traversal is flipped rather
    than deleted because the sequence is what proves the repair holds.

    WHAT IT FOUND: `poll_history` called `self._symbols.setdefault(symbol,
    _SymbolFeedState())`, so polling created a full subscription record for a symbol nobody
    subscribed. `_SymbolFeedState` is documented as *"Everything this adapter knows about ONE
    subscription"* and stopped being true; `granted_mode(None)`'s pessimism — justified on the
    grounds that *"a single mode reported for a set that does not share one is a fabricated
    value"* — was applied to a set a poll had silently widened; and a later `unsubscribe`
    issued a REAL `cancelMktData` for a subscription that never existed.

    THE COLLAPSE ITSELF WAS FAIL-CLOSED and was never the harm; the `cancelMktData` was. A real
    vendor call for a subscription this library never made, on a clientId whose whole argument
    (`DATAFEED_CLIENT_ID`, and the 0/1 refusals) is that venue-side activity must be
    unambiguously attributable to one library's intent.

    THE REPAIR: the poll path has its own map of its own type — `_polled: dict[Symbol,
    _SymbolPollState]` — and no member of it can reach `cancelMktData`, `granted_mode` or
    `reqMktData`. What the poll needs to record is a POLL observation, so it is not named or
    typed as a subscription.
    """
    ad, _, fake = await new_ad(history=lambda s: [bar_row(100.0)])
    await ad.subscribe(SYM)
    nonvac(
        ad.granted_mode() is MarketDataMode.DELAYED,
        "the adapter-wide grant did not start from a known mode — nothing can be seen to "
        "collapse",
    )
    nonvac(
        OTHER not in ad._symbols, "the second symbol was already known to the adapter"
    )

    await ad.poll_history(OTHER)

    # THE REPAIR, in the same three observables the defect was reported in.
    assert OTHER not in ad._symbols
    assert ad.polled_symbols() == (OTHER,)  # recorded, and recorded as a POLL
    assert ad.granted_mode() is MarketDataMode.DELAYED  # unmoved by an unrelated poll
    assert ad.granted_mode(SYM) is MarketDataMode.DELAYED

    await ad.unsubscribe(OTHER)
    assert fake.cancelled == []  # nothing on the wire for a symbol never subscribed
    assert OTHER not in fake.subscribed
    # CONTROL: the real subscription still cancels, so this is not "unsubscribe stopped
    # working" — the two verdicts a can-fail needs (debug.md §7.1).
    await ad.unsubscribe(SYM)
    assert fake.cancelled == [SYM]


# ===========================================================================
# T12 — RETRY AFTER A PARTIAL FAILURE (§5.5: failure AFTER a side effect)
#        ADDED. Reason: §5.1 names "an operation retried after a partial failure" and the
#        brief's ten have no sequence in which a side effect has already landed when the
#        failure arrives. `_ingest_history` seals and THEN publishes, so the window exists.
# ===========================================================================


@pytest.mark.asyncio
async def test_t12_a_consumer_that_raises_mid_ingest_owes_a_publication_it_can_recover() -> (
    None
):
    """SEQUENCE: poll returning four bars into a sink whose `on_bar` raises on the third ->
    retry the same poll with a healthy sink.

    PRECONDITIONS: a live subscription; a history source returning four distinct bars; a sink
      that raises `RuntimeError` on its third `on_bar` and is then repaired.
    EXPECTED END STATE (determined by the repair below): the poll raises out to the caller.
      Three bars are SEALED, two were PUBLISHED, the third is OWED and readable as owed, and
      the attempt is recorded `ok=False, undelivered=1`. On the retry the owed seal is
      RE-PUBLISHED — the same object, not a re-derived one — and the debt clears.
    OBSERVABLE: `sealed_bars()` versus the sink's `bars` after each step, `unpublished_seals()`,
      and `poll_attempts()`.

    FINDING — CODE DEFECT, the sharpest one this suite found, **CLOSED IN ARC 023 (F13)**. The
    traversal is flipped rather than deleted: the sequence is what proves the repair, and a
    partial failure that has already had a side effect is the only sequence that can.

    WHAT IT FOUND, TWO DEFECTS. `_ingest_history` wrote the seal store BEFORE it published:
    `self._sealed[key] = bar` then `self._sink.on_bar(bar)`. The seal is what makes the poll
    path idempotent, which is genuinely good — the retry duplicates nothing. But the seal was
    also what made the publication UNREPEATABLE, so a publication that failed could never be
    re-attempted: on every later poll the bar was "already sealed", identical, and dropped as a
    no-op re-poll. D1.14's rule is *seal and never rewrite*; the consequence nobody wrote down
    was *seal and never re-publish*. And the second defect sat on top of it: the attempt record
    said `ok=True, rows=4` — full success for a poll whose consumer received half of it.

    THE REPAIR IS A PUBLICATION DEBT, NOT A RE-DERIVATION, and the distinction is load-bearing.
    `self._unpublished` holds the seal keys the sink has not accepted; the next poll to reach
    the key re-publishes the SEALED OBJECT with its original `seal_seq`, `recv_ts` and payload.
    Rebuilding the bar from the retry's row was the tempting fix and is worse than the defect:
    the retry's row may carry the venue's REVISED values, so a re-derived bar would seal a
    revision as though it were the original and the revision fact — observable only here
    (`docs/SPEC-AMENDMENTS.md` AMENDMENT 4) — would vanish. D1.14 is intact.

    `ok` NARROWED AND `venue_answered` WAS ADDED rather than `ok` being overloaded: *the venue
    answered* and *everything it returned reached the sink* are two facts, and one field
    carrying both is the `avg_price` shape `docs/CHECK-DEBT.md` D1.29 records.
    """

    class BlowsUp(RecordingFeedSink):
        limit: int = 2

        def on_bar(self, sealed):
            if len(self.bars) >= self.limit:
                raise RuntimeError("consumer blew up")
            super().on_bar(sealed)

    rows = [bar_row(100.0), bar_row(160.0), bar_row(220.0), bar_row(280.0)]
    sink = BlowsUp()
    fake = FakeIBFeed()
    ad = IBKRBrokerDatafeed(sink, ib=fake, history_source=lambda s: list(rows))
    fake.bind(ad)
    assert ad._sink is sink and ad._ib is fake
    await ad.connect()
    await ad.subscribe(SYM)

    with pytest.raises(RuntimeError):
        await ad.poll_history(SYM)

    # NON-VACUITY: the tear must be real — a side effect landed BEFORE the failure.
    nonvac(
        len(ad.sealed_bars()) == 3 and len(sink.bars) == 2,
        f"no partial ingest occurred (sealed={len(ad.sealed_bars())} "
        f"published={len(sink.bars)}) — there is nothing to retry after",
    )

    # DEFECT 2 CLOSED: the attempt cannot report success over the loss, and the transport fact
    # it used to stand for is still readable under its own name.
    attempt = ad.poll_attempts()[-1]
    assert (attempt.ok, attempt.venue_answered, attempt.rows) == (False, True, 4)
    assert (attempt.sealed, attempt.published, attempt.undelivered) == (3, 2, 1)

    # DEFECT 1, HALF ONE: the loss is a VALUE while it lasts, not an absence of evidence.
    owed = ad.unpublished_seals()
    assert [b.seal_key for b in owed] == [(SYM, 220.0, 60.0)]

    sink.limit = 99  # the consumer recovers
    assert await ad.poll_history(SYM) == 4

    # THE RELATION THAT HOLDS: the venue side is idempotent — one seal per key, no duplicates.
    keys = [b.seal_key for b in ad.sealed_bars()]
    assert len(keys) == len(set(keys)) == 4

    # DEFECT 1, HALF TWO: nothing is lost, and what came back is the SEAL and not a rebuild.
    published = {b.seal_key for b in sink.bars}
    sealed = {b.seal_key for b in ad.sealed_bars()}
    assert sealed - published == set()
    assert ad.unpublished_seals() == ()
    recovered = next(b for b in sink.bars if b.seal_key == (SYM, 220.0, 60.0))
    assert recovered is owed[0]  # identity, not equality — D1.14's seal, re-published
    assert sink.bar_revisions == []  # and no revision was invented to carry it
    assert ad.poll_attempts()[-1].ok is True


# ===========================================================================
# T13 — BOUNDS ON THE RETRY BUDGET (§5.3)
#        ADDED. Reason: §5.3 requires every parameter's real limits to be established.
#        `poll_attempts` is the only tunable this adapter validates, and the per-call
#        override of it is validated nowhere.
# ===========================================================================


@pytest.mark.asyncio
async def test_t13_constructor_floor_on_the_retry_budget_holds_at_every_edge() -> None:
    """BOUNDS, §5.3: minimum, first illegal value, and just-inside for `poll_attempts`.

    PRECONDITIONS: none — this is construction-time.
    EXPECTED END STATE: 1 is the floor and is accepted; 0 and negatives are refused with
      `ValueError`; the refusal names the spec obligation it protects.
    OBSERVABLE: the exception type, and `poll_attempts()`'s length after a run at the floor.
    """
    for illegal in (0, -1, -1000):
        with pytest.raises(ValueError):
            IBKRBrokerDatafeed(RecordingFeedSink(), poll_attempts=illegal)

    # Just inside: exactly one attempt, and it must really be one — not zero.
    calls: list[str] = []

    def once(symbol):
        calls.append(symbol)
        raise RuntimeError("venue timeout")

    ad, _, _ = await new_ad(history=once, poll_attempts=1)
    await ad.subscribe(SYM)
    with pytest.raises(FeedPollExhausted):
        await ad.poll_history(SYM)
    assert calls == [SYM]
    assert len(ad.poll_attempts()) == 1


@pytest.mark.xfail(
    strict=True,
    reason=(
        "FINDING — CODE DEFECT, spec-determined. poll_history(attempts=0) raises "
        "FeedPollExhausted having made ZERO venue calls, so 'the retry budget was exhausted' "
        "is reported for a poll that never retried anything. See the test docstring."
    ),
)
@pytest.mark.asyncio
async def test_t13b_exhaustion_is_never_declared_without_a_single_attempt() -> None:
    """SEQUENCE: `poll_history(SYM, attempts=0)`, and again with a negative budget.

    PRECONDITIONS: a live session, a subscribed symbol, and a history source that WOULD succeed
      — so a failure cannot be attributed to the venue.
    EXPECTED END STATE (determined, see below): whatever the adapter does with a zero budget, it
      does not declare exhaustion, because declaring exhaustion is a measurement.
    OBSERVABLE: the invariant *if `FeedPollExhausted` was raised then `poll_attempts()` is
      non-empty*. Observed: it is raised with an EMPTY attempt log and zero venue calls.

    THE AUTHORITY THAT DETERMINES THIS — this is one of only two `strict=True` markers in the
    file, so the authority is named rather than assumed. `nics_risk_subsystem_spec_v1.3.md`
    §6.4:373-374 makes stale mean *"(freshness stamp past threshold, AFTER RETRY/BACKOFF) => halt
    new entries AND flatten open"*, §12A:827 names the `RETRY_BACKOFF` tunable, and §13:900
    repeats the requirement. `poll_history`'s own docstring cites all three as the reason its
    bounded loop exists. A `FeedPollExhausted` raised without one attempt asserts that the retry
    policy ran and failed, when it did not run — and the consumer's next step under §6.4 is a
    liquidation. debug.md §7.9 is the second half: this is CANNOT MEASURE wearing FAIL's clothes,
    which is the precise defect §7.9's own real incident records.

    THE CONSTRUCTOR ALREADY SETTLED THE QUESTION and its message says why: a budget below 1
    *"would make the poll fallback — the ONLY market-data path at Stage 0 — do nothing"*. The
    keyword-only per-call override reaches around that floor with no validation at all.

    THE ASSERTION IS REMEDY-NEUTRAL ON PURPOSE. Refusing the argument, clamping to the floor, or
    raising a distinct CANNOT-MEASURE error are all defensible repairs and this test passes under
    every one of them, because it asserts only that exhaustion is not declared over nothing.
    """
    calls: list[str] = []

    def good(symbol):
        calls.append(symbol)
        return [bar_row(100.0)]

    ad, _, _ = await new_ad(history=good)
    await ad.subscribe(SYM)
    nonvac(
        await ad.poll_history(SYM) == 1 and calls == [SYM],
        "the history source is not working, so a later failure would be the source's and not "
        "the budget's",
    )

    for budget in (0, -3):
        # THE BASELINE IS DERIVED PER ITERATION, never a literal (§7.4). The successful poll
        # above already put one row in the attempt log, so "the log is non-empty" would be
        # satisfied by history — the question is whether THIS call recorded anything.
        attempts_before = len(ad.poll_attempts())
        calls_before = len(calls)
        raised = None
        try:
            await ad.poll_history(SYM, attempts=budget)
        except FeedPollExhausted as exc:
            raised = exc
        if raised is None:
            continue
        assert len(ad.poll_attempts()) > attempts_before, (
            f"attempts={budget}: FeedPollExhausted declared having recorded no attempt at all "
            f"and made {len(calls) - calls_before} venue call(s) — exhaustion reported over a "
            "measurement that never happened"
        )


# ===========================================================================
# T14 — CORNER CASE: a payload value that is not equal to itself (§5.5)
#        ADDED. Reason: §5.5 requires corner cases to be enumerated deliberately. The
#        seal/revision machinery rests entirely on `==` over the payload tuple, and there
#        is exactly one float that breaks `==`.
# ===========================================================================


@pytest.mark.xfail(
    strict=True,
    reason=(
        "FINDING — CODE DEFECT. An identical re-poll whose payload carries NaN publishes a "
        "BarRevision on EVERY poll, defeating BarRevision.__post_init__'s own guard. See the "
        "test docstring for the authority and the control."
    ),
)
@pytest.mark.asyncio
async def test_t14_identical_repoll_carrying_nan_publishes_endless_revisions() -> None:
    """SEQUENCE: poll the same bar four times, where one payload field is `float('nan')`.

    PRECONDITIONS: a live subscription; a history source that REBUILDS its row per call, which
      is what a real vendor read does. (Reusing one dict hides this defect entirely — CPython's
      tuple comparison short-circuits on identity, so the same `nan` OBJECT compares equal to
      itself. That draft passed, and it is recorded in the module docstring's can-fail evidence.)
    EXPECTED END STATE (determined, see below): one seal and ZERO revisions — the venue said the
      same thing four times.
    OBSERVABLE: the sink's `bars` and `bar_revisions` counts, and each revision's
      `differing_fields`.

    THE AUTHORITY THAT DETERMINES THIS is the second of the file's two `strict=True` markers,
    and it is a runtime guard in `broker_seam.py` whose own docstring declares the rule:
    `BarRevision.__post_init__` refuses a revision with no differing field, because *"an
    identical re-poll is not a revision, and reporting one would bury the real ones"*.
    `_ingest_history` states the same rule: *"if it is identical, it is dropped, because an
    identical re-poll is not a revision and a stream of no-op revisions is how a real one becomes
    invisible."* Both are defeated by NaN: `_maybe_revise` computes `revised != sealed.payload()`,
    which is TRUE for bit-identical NaN, so `differing_fields` is non-empty and the guard's own
    `revised_payload == sealed.payload()` check also passes. The failure mode the guard was
    written to prevent — a stream of no-op revisions burying a real one — is produced by the
    guard's own comparison operator.

    REACHABILITY IS STATED AT ITS REAL GRADE (debug.md failure mode #12). NaN is not measured on
    this system's history path; no bar poll has ever run against the live venue. `ib_async`
    represents absent doubles as `nan` on its `Ticker` surface, and the `history_source` row
    contract is undocumented — nothing anywhere says what a row may contain. The defect is
    STRUCTURAL and does not depend on the vendor: any payload float that is not equal to itself
    produces it, and `_require_ohlc` — which refuses a MISSING field — admits NaN without a word.

    THE CONTROL IS IN THIS TEST, not beside it: the same driver, the same four polls, without
    NaN, must report ZERO revisions. Without that arm, "revisions appeared" is indistinguishable
    from a driver that always revises.
    """
    # CONTROL ARM FIRST (§7.1): the driver does not invent revisions.
    control_ad, control_sink, _ = await new_ad(history=lambda s: [bar_row(100.0)])
    await control_ad.subscribe(SYM)
    for _ in range(4):
        await control_ad.poll_history(SYM)
    nonvac(
        len(control_sink.bars) == 1,
        "the control never sealed a bar, so its zero-revision result means nothing",
    )
    assert control_sink.bar_revisions == [], (
        "the CONTROL produced revisions for identical rows — the driver revises unconditionally "
        "and the NaN arm below would prove nothing"
    )

    # THE SUBJECT ARM: one field that is not equal to itself, rebuilt per poll.
    def nan_rows(symbol):
        return [dict(bar_row(100.0), high=float("nan"))]

    ad, sink, _ = await new_ad(history=nan_rows)
    await ad.subscribe(SYM)
    for _ in range(4):
        await ad.poll_history(SYM)

    nonvac(len(sink.bars) == 1, "the NaN arm never sealed a bar")
    nonvac(
        math.isnan(sink.bars[0].high),
        "the sealed bar does not carry a NaN — the corner case was never reached",
    )
    MEASURED["nan_revisions_per_4_identical_polls"] = len(sink.bar_revisions)
    assert sink.bar_revisions == [], (
        f"{len(sink.bar_revisions)} revision(s) published for four IDENTICAL re-polls: "
        f"{[r.differing_fields for r in sink.bar_revisions]}"
    )


# ===========================================================================
# T15 — ONE NUMBER, TWO MEANINGS, AT THE PORT VERB
#        ADDED. Reason: every sequence in the brief's ten is single-symbol, and the port's
#        zero-argument `feed_lag()` only becomes expressible with two.
# ===========================================================================


@pytest.mark.asyncio
async def test_t15_adapter_wide_feed_lag_averages_across_symbols_the_module_says_it_must_not() -> (
    None
):
    """SEQUENCE: subscribe two symbols granted DIFFERENT modes -> one tick each, with wildly
    different lags -> read `feed_lag()` with no symbol, which is the PORT verb's own signature.

    PRECONDITIONS: two live subscriptions with genuinely different granted modes and genuinely
      different observed lags (600 s and 1 s).
    EXPECTED END STATE: undetermined for the lag. Observed: `granted_mode()` correctly refuses
      to pick one mode and answers UNKNOWN, while `feed_lag()` averages the two symbols' samples
      into a single `observed_lag_s` of 300.5 s — a figure true of neither feed — and reports it
      as `provenance=OBSERVED, observed_n=2`.
    OBSERVABLE: `feed_lag()` versus `feed_lag(SYM)` and `feed_lag(OTHER)`.

    FINDING — INTERNAL CONTRADICTION, and the module names the defect itself, one method away.
    `evaluate_freshness` explains why it works per symbol: *"Per-symbol lag, not an adapter-wide
    one: two subscriptions can be granted different modes (see `granted_mode`), and averaging
    their samples would produce a lag figure true of neither."* `feed_lag(None)` — the only
    spelling `BrokerDatafeedPort.feed_lag(self) -> FeedLag` can be called with, and therefore the
    only spelling a port-typed consumer HAS — does precisely that averaging. `granted_mode(None)`
    took the opposite route for the identical situation and returns UNKNOWN rather than a
    fabricated single value, with a docstring saying so.

    THE SHAPE IS `avg_price` AT MODULE SCALE — one number carrying two meanings — which this
    module's own docstrings cite three separate times as the thing they exist to prevent
    (`docs/CHECK-DEBT.md` D1.29 is its third recorded instance).

    NO REMEDY ASSERTED, and the reason is real rather than procedural: the pessimistic answer
    `granted_mode` uses has no analogue for a float. `None`/UNOBSERVED, the max, and refusing
    the zero-argument form are all defensible, and `nics_risk_subsystem_spec_v1.3.md` §2A:86-92
    declares no lag concept at all, so nothing determines it. THE SECTION THAT WOULD HAVE TO SAY
    IT is §2A's broker-datafeed declaration, in the same v1.4 that would adopt `feed_lag` as a
    ratified addition rather than a flagged one.
    """
    ad, _, fake = await new_ad(grant_map={3: 3})
    await ad.subscribe(SYM)
    ad._requested_mode = MarketDataMode.DELAYED_FROZEN
    fake.grant_map = {4: 4}
    await ad.subscribe(OTHER)

    # ARC 023: both symbols are fed inside ONE `LAG_WINDOW_S`, and that is a precondition the
    # traversal now has to meet rather than a detail. The adapter-wide read re-windows every
    # symbol's samples together, so two symbols whose packets are further apart in RECEIPT time
    # than the window cannot co-exist in it — and the average would then be one symbol's figure
    # wearing the adapter-wide name, which is a different (and quieter) defect from this one.
    saturate(ad, SYM, lag=600.0, base_recv=700.0)  # 600 s behind
    saturate(ad, OTHER, lag=1.0, base_recv=700.0)  # 1 s behind

    # NON-VACUITY: the two subscriptions must genuinely differ, or there is nothing to average
    # ACROSS and the traversal degrades into a one-symbol read.
    nonvac(
        ad.granted_mode(SYM) is not ad.granted_mode(OTHER),
        f"both symbols were granted {ad.granted_mode(SYM)} — the traversal cannot express a "
        "mixed-grant adapter",
    )
    per_symbol = (ad.feed_lag(SYM).observed_lag_s, ad.feed_lag(OTHER).observed_lag_s)
    nonvac(
        per_symbol == (600.0, 1.0),
        f"the per-symbol lags are {per_symbol} — they do not differ enough for an average to be "
        "distinguishable from either",
    )

    # THE CONTRAST, asserted as a relation between the two adapter-wide readers.
    assert ad.granted_mode() is MarketDataMode.UNKNOWN  # refuses to fabricate
    wide = ad.feed_lag()
    assert wide.granted_mode is MarketDataMode.UNKNOWN
    assert wide.provenance is LagProvenance.OBSERVED
    assert wide.observed_n == 2 * LAG_SAMPLE_FLOOR
    assert wide.observed_lag_s == sum(per_symbol) / 2
    assert wide.observed_lag_s not in per_symbol  # true of neither feed
    MEASURED["adapter_wide_lag_vs_per_symbol"] = (wide.observed_lag_s, per_symbol)


# ===========================================================================
# T16 — SCALE (§5.4): measured, not extrapolated
#        ADDED. Reason: §5.4 is a required half of Tier 3 and none of the brief's ten
#        sequences reaches it. `lag_samples` is the only unbounded per-item structure in
#        the module.
# ===========================================================================


@pytest.mark.asyncio
async def test_t16_the_lag_window_is_bounded_and_a_recent_degradation_is_visible() -> (
    None
):
    """SCALE, §5.4: drive the tick path at volume and measure growth, cost and sensitivity.

    PRECONDITIONS: one live subscription. N healthy packets (lag 600 s, matching the banked
      ARC 013 figure) followed by M degraded ones at 900 s — a feed that has fallen 50% further
      behind, which is 60 times the `divergence_tolerance_s` the object itself carries. The
      packets carry a MONOTONIC receipt clock, one per second, because the window trims by TIME.
    EXPECTED END STATE (determined by the repair below): retained samples are bounded by the
      window and not by the packet count, and the reading reports DIVERGED over the degraded
      tail while the separately-named session figure still shows the dilution.
    OBSERVABLE: `feed_lag(SYM).window` against packets delivered; `agreement`;
      `session_mean_lag_s` beside `observed_lag_s`; wall time recorded, asserted on nowhere.

    FINDING — CODE DEFECT with a scale consequence, **CLOSED IN ARC 023 (F17)**. Flipped rather
    than deleted: volume is the only thing that can show a bound holding.

    WHAT IT FOUND, two halves and one structure:
      (a) UNBOUNDED GROWTH. `lag_samples` held one float per tick, per symbol, for the life of
          the process, and `feed_lag()` was O(n) in it — a Limiter reading freshness every
          cycle paid a cost that rose for the whole session (`debug.md` §5.4: *"anything
          per-item that is not released is a leak that only appears at scale"*).
      (b) THE MEAN WAS THE WRONG STATISTIC FOR THE QUESTION ASKED OF IT, and it was wrong IN
          THE DIRECTION THAT MATTERS: the session-wide mean read AGREES at 602.97 s while the
          last hundred packets sat at 900 s, sixty tolerances outside. It said the feed agreed
          while the feed had degraded by 300 s. The dilution is arithmetic, so the longer the
          session had been healthy the harder a real degradation was to see.

    THE REPAIR, and every number in it was MEASURED in ARC 023 rather than chosen:
      * the window is bounded BY TIME (`LAG_WINDOW_S` = 60 s), not by count. A 100-sample count
        window spans 222.2 s at ARC 013's measured rate (18 ticks / 40 s) and 0.000028 s at this
        box's measured ingest ceiling (3,561,839 samples/s) — one count cannot mean one thing at
        both ends of that range (`debug.md` §7.4).
      * a SAMPLE FLOOR (`LAG_SAMPLE_FLOOR` = 5): below it the object declares ABSENCE rather
        than a mean over too few, and it does NOT fall back to the session figure (AMENDMENT 3).
        At ARC 013's rate the floor is reached in 11.1 s and the window holds 27 samples.
      * memory is bounded REGARDLESS OF RATE, which a time window alone does not achieve — at
        the ingest ceiling a pure 60 s window would retain 213,710,318 samples = 20.5 GB. So a
        COUNT backstop exists, and WHICH BOUND APPLIED is readable off `LagWindow.bound`.
      * the session-wide figure is retained, INFORMATIONAL, and separately named
        (`FeedLag.session_mean_lag_s`). Nothing decides on it.
      * detection at ARC 013's measured rate: the windowed reading goes DIVERGED after the
        FIRST degraded packet (2.2 s), where the session-wide mean never did.

    NOTHING BELOW IS ASSERTED AGAINST A MEASURED NUMBER (§7.4). The relations are asserted; the
    numbers go to `MEASURED` for the arc report.
    """
    healthy, degraded = 10_000, 100
    healthy_lag, degraded_lag = 600.0, 900.0
    ad, sink, _ = await new_ad()
    await ad.subscribe(SYM)

    start = time.perf_counter()
    for i in range(healthy):
        ad._on_ib_tick(SYM, 1.0, 1.0, float(i), recv_ts=float(i) + healthy_lag)
    for i in range(healthy, healthy + degraded):
        ad._on_ib_tick(SYM, 1.0, 1.0, float(i), recv_ts=float(i) + degraded_lag)
    ingest_s = time.perf_counter() - start

    store = ad._symbols[SYM].lag_window
    nonvac(
        len(sink.ticks) == healthy + degraded,
        f"only {len(sink.ticks)} packets reached the sink — the volume was never delivered",
    )
    nonvac(
        store.session_n == healthy + degraded,
        f"only {store.session_n} samples were recorded at all — the volume never reached the "
        "window under measurement",
    )

    t0 = time.perf_counter()
    whole = ad.feed_lag(SYM)
    read_s = time.perf_counter() - t0
    win = whole.window
    assert win is not None

    # (a) THE RELATION, not a number: retention is bounded by the WINDOW, not by the packet
    # count, and the bound that applied is readable.
    assert win.n_in_window < healthy + degraded
    assert win.span_s is not None and win.span_s <= LAG_WINDOW_S
    assert win.bound is LagWindowBound.TIME
    assert win.n_in_window <= win.max_samples

    # (b) THE RELATION THAT WAS INVERTED BEFORE: the reading follows the RECENT packets, and
    # the session figure — which nothing decides on — still shows the dilution the old
    # observable reported as agreement.
    nonvac(
        abs(degraded_lag - (whole.declared_lag_s or 0.0))
        > whole.divergence_tolerance_s,
        f"the degraded packets ({degraded_lag} s) are not actually outside the tolerance "
        f"({whole.divergence_tolerance_s} s) — the traversal never degraded the feed",
    )
    assert whole.agreement is LagAgreement.DIVERGED
    assert whole.observed_lag_s == degraded_lag
    assert whole.session_mean_lag_s is not None
    assert whole.session_mean_lag_s < whole.observed_lag_s
    assert (
        whole.effective_lag_s == whole.observed_lag_s
    )  # the WINDOW decides, not the session

    MEASURED["scale"] = {
        "ticks": healthy + degraded,
        "ingest_s": round(ingest_s, 4),
        "ticks_per_s": round((healthy + degraded) / ingest_s),
        "retained_samples": win.n_in_window,
        "retained_span_s": win.span_s,
        "window_bound": win.bound.value,
        "feed_lag_read_s": round(read_s, 6),
        "windowed_mean_s": whole.observed_lag_s,
        "session_mean_s": whole.session_mean_lag_s,
        "windowed_agreement": whole.agreement.value,
    }
    print(f"\n§5.4 MEASURED: {MEASURED['scale']}")


# ===========================================================================
# T17 — THE SAME OPERATION TWICE, ON THE SESSION VERBS
#        ADDED. Reason: the brief's ten cover repeat `subscribe` but not repeat
#        `connect`/`disconnect`, and the session verbs are where D1.24-class state
#        lifetime defects live.
# ===========================================================================


@pytest.mark.asyncio
async def test_t17_repeat_session_verbs_republish_transitions_that_did_not_happen() -> (
    None
):
    """SEQUENCE: connect -> connect; disconnect -> disconnect; and disconnect on an adapter that
    was never connected.

    PRECONDITIONS: a fresh adapter per arm, so the arms cannot contaminate each other.
    EXPECTED END STATE: undetermined. Observed: every call publishes `on_feed_status`
      unconditionally, so a second `connect()` emits a second UP, a second `disconnect()` emits
      a second DOWN, and a `disconnect()` on a never-connected adapter emits a DOWN for a
      session that never existed. The second `connect()` also drives `self._ib.connect(...)` a
      second time, which on a live IBKR clientId is an error rather than a no-op.
    OBSERVABLE: the sink's `feed_statuses`, and the fake's `connected` flag.

    FINDING — SPEC GAP, and the gap is visible in the frozen text itself, EIGHT LINES APART.
    `nics_risk_subsystem_spec_v1.3.md` §2A:84 declares `on_session(up|down, reason?)` — *"
    connectivity TRANSITIONS (drives cold-start / Sentinel)"*. §2A:92 declares
    `on_feed_status(up|down|stale, symbol?, reason?)` — *"drives the stale=>halt+flatten path"* —
    and the word "transitions" is ABSENT. So the order path has an edge semantics in the frozen
    document and the datafeed has none, and the adapter's level semantics is neither compliant
    nor non-compliant with a sentence that was never written.

    THE ORDER PATH ALREADY BANKED THIS AS A DEFECT, one library over, which is why the datafeed
    version cannot be waved past: `docs/CHECK-DEBT.md` D1.28 item (c) reads *"`disconnect()`
    emits `on_session(DOWN)` on every call including when there was never a session, while
    `nics_risk_subsystem_spec_v1.3.md` §2A defines `on_session` as connectivity TRANSITIONS"* —
    arm C below is that finding, verbatim, on the second library. It was reachable there because
    §2A:84 says "transitions"; here it is a gap instead of a defect purely because §2A:92 does
    not.

    `_publish_feed_state` is documented as *"The ONE emission site"* and its argument is that
    four writers with four emission sites is four chances to publish a state one is not entitled
    to. The choke point is real; what it does not do is DEDUPLICATE, and nothing says whether it
    should. THE SECTION THAT WOULD HAVE TO SAY IT is §2A:92 itself — one word, the one §2A:84
    already has.
    """
    # ARM A — connect twice.
    ad, sink, fake = await new_ad()
    nonvac(
        [s[0] for s in sink.feed_statuses] == [FeedState.UP],
        "the first connect published nothing — the arm has no baseline",
    )
    await ad.connect()
    assert [s[0] for s in sink.feed_statuses] == [FeedState.UP, FeedState.UP]
    assert fake.connected

    # ARM B — disconnect twice.
    ad2, sink2, _ = await new_ad()
    await ad2.disconnect()
    await ad2.disconnect()
    assert [s[0] for s in sink2.feed_statuses] == [
        FeedState.UP,
        FeedState.DOWN,
        FeedState.DOWN,
    ]

    # ARM C — disconnect a session that never existed.
    ad3, sink3, _ = await new_ad(connect=False)
    nonvac(sink3.feed_statuses == [], "arm C was connected after all")
    await ad3.disconnect()
    assert [s[0] for s in sink3.feed_statuses] == [FeedState.DOWN]


# ===========================================================================
# T18 — BOUNDS AT THE SEAM'S OWN EDGES (§5.3)
#        ADDED. Reason: §5.3 requires every input's real limits, and asks explicitly what
#        happens BEYOND them. `Bar.__post_init__` validates exactly one field.
# ===========================================================================


def test_t18_a_bar_is_validated_on_provenance_and_on_nothing_else() -> None:
    """BOUNDS, §5.3: minimum / illegal / incoherent values on every `Bar` field.

    PRECONDITIONS: none — direct construction at the seam, which is where a consumer meets it.
    EXPECTED END STATE: undetermined for every field except `source`. Observed: `Bar` refuses a
      non-venue `source` loudly (AMENDMENT 4, by allowlist) and accepts EVERY other degenerate
      value — `period_s=0` and negative, a negative `bar_start_venue_ts`, `high` below `low`,
      `close` outside `[low, high]`, and infinities.
    OBSERVABLE: whether construction raises, and the resulting `seal_key`.

    FINDING — SPEC GAP, with a live asymmetry inside the module. `docs/SPEC-AMENDMENTS.md`
    AMENDMENT 3's ARC 022 refinement decided what an ABSENT payload field means — it is a
    MALFORMED ROW, refused by `_require_ohlc` with the symbol and the field named. It took no
    view on an INCOHERENT one, and `_require_ohlc` tests only `row.get(f) is None`. So a venue
    row saying `high < low` is admitted, sealed, published, and becomes half of a `seal_key`,
    while a row omitting `high` is refused — and the second is arguably the less wrong of the
    two, because it is at least legible as an error.

    `period_s` IS THE SHARPER HALF because it is part of the SEAL KEY. `period_s=0` makes every
    bar opening at one instant a single key regardless of its real period, which is exactly the
    collision `period_s`'s own docstring exists to prevent: *"Without it a 1-minute and a
    5-minute bar opening at the same instant are the same bar."*

    §5.3 SAYS UNDEFINED IS A CERTIFICATION FAILURE, and this is reported as one rather than
    softened. THE SECTION THAT WOULD HAVE TO SAY IT: `docs/SPEC-AMENDMENTS.md` AMENDMENT 3's
    refinement, which owns the malformed-row concept, in the same v1.4 §2A entry. NO ANSWER IS
    INVENTED — whether the seam validates venue numbers at all is a real argument (the adapter's
    standing position is that the venue is the source and Nix does not second-guess it), and
    that argument has not been had.
    """

    def make(**over):
        base = {
            "symbol": SYM,
            "bar_start_venue_ts": 100.0,
            "period_s": 60.0,
            "open": 1.0,
            "high": 2.0,
            "low": 0.5,
            "close": 1.5,
            "volume": 10.0,
            "recv_ts": 1.0,
            "source": BarSource.POLLED_HISTORY,
            "seal_seq": 1,
        }
        base.update(over)
        return Bar(**base)

    # THE ONE VALIDATED FIELD — refused by allowlist, and the refusal names the amendment.
    with pytest.raises(ValueError):
        make(source=BarSource.TICK_AGGREGATED)
    nonvac(
        make() is not None,
        "the baseline bar does not construct — every arm below is vacuous",
    )

    # EVERY OTHER EDGE — accepted without a word.
    assert make(period_s=0.0).seal_key == (SYM, 100.0, 0.0)
    assert make(period_s=-60.0).period_s == -60.0
    assert make(bar_start_venue_ts=-1.0).seal_key[1] == -1.0
    assert make(high=0.0, low=9.0).high < make(high=0.0, low=9.0).low
    assert make(close=1e9).close == 1e9
    assert math.isinf(make(open=float("inf")).open)

    # AND THE COLLISION THAT MAKES period_s LOAD-BEARING: two different periods, one key.
    assert make(period_s=0.0).seal_key == make(period_s=0.0, close=99.0).seal_key


# ===========================================================================
# T19 — THE OPTIONAL FIELD WHOSE OBSERVABLE ABSENCE IS NEVER OBSERVED
#        ADDED. Reason: AMENDMENT 3's refinement landed in this arc and is the newest
#        rule in the module. §5.7 says the newest instruments are the ones to check.
# ===========================================================================


@pytest.mark.asyncio
async def test_t19_the_ibkr_not_reported_volume_sentinel_is_translated_at_the_boundary() -> (
    None
):
    """SEQUENCE: poll a history row whose `volume` is IBKR's documented not-reported sentinel.

    PRECONDITIONS: a live subscription and a history source returning `volume=-1.0`, which
      `Bar.volume`'s own docstring names as *"IBKR returns `BarData.volume = -1` — its own
      not-reported sentinel — for bar types where volume is not a fact about the bar"*.
    EXPECTED END STATE (determined by the repair below): `-1.0` is TRANSLATED into the absence
      it denotes, so the sealed bar's `volume` is `None` and the sentinel does not cross.
    OBSERVABLE: the sealed bar's `volume`; and the control arm, where a genuinely absent key
      also produces `None`.

    FINDING — SPEC/CONTRACT GAP, **the code half CLOSED IN ARC 023 (D1.39/D1.40)**; the
    contract half is still open and is reported below.

    WHAT IT FOUND: `Bar.volume` keeps its `| None` under AMENDMENT 3's refinement on the
    strength of one justification — the `-1` sentinel is the OBSERVABLE ABSENCE that earns the
    optional — and nothing in the module translated `-1` into that absence. A consumer doing
    arithmetic on `volume` could receive `-1.0` and read it as *one contract traded, short*,
    which is the substitution AMENDMENT 3 forbids arriving through the field the amendment kept
    optional in order to prevent it.

    THE REPAIR: `broker_datafeed_ibkr._volume` translates `IB_VOLUME_NOT_REPORTED` at the
    VENDOR boundary, which is where it belongs — a sentinel is a vendor type wearing a float's
    clothes, and §2A:104-105 invariant 2 keeps vendor types off the seam. Only the ONE
    documented sentinel is translated; a value no document assigns a meaning to does not
    acquire one here.

    STILL OPEN, AND IT IS THE MORE BASIC HALF: `history_source` is an INJECTED callable with NO
    declared row contract — key names, types and sentinel handling are nowhere specified, and
    `_require_ohlc` plus `_volume` now enforce two clauses of a contract that otherwise does
    not exist. THE SECTION THAT WOULD HAVE TO SAY IT is a declared row contract, which has no
    home today.

    EVIDENCE GRADE, UNCHANGED BY THE REPAIR and stated (debug.md failure mode #12): the `-1`
    sentinel is IBKR-DOCUMENTED and NOT MEASURED on this system. Translating a declaration does
    not promote it to a measurement; it stays VENDOR_DECLARED and known-red against the tap in
    `~/nix/downloads/tap_session_runbook.md`.
    """
    ad, sink, _ = await new_ad(history=lambda s: [bar_row(100.0, v=-1.0)])
    await ad.subscribe(SYM)
    await ad.poll_history(SYM)
    nonvac(
        len(sink.bars) == 1, "nothing was sealed — the sentinel never reached the seam"
    )

    # THE REPAIR: the sentinel does NOT cross as a number.
    assert sink.bars[0].volume is None

    # THE CONTROL: a genuinely absent key DOES produce the declared absence, so the optional is
    # reachable and this is a translation gap and not a dead field.
    row = bar_row(200.0)
    del row["volume"]
    ad2, sink2, _ = await new_ad(history=lambda s: [dict(row)])
    await ad2.subscribe(SYM)
    await ad2.poll_history(SYM)
    assert sink2.bars[0].volume is None


# ===========================================================================
# T20 — THE ONLY WORKING STAGE 0 DATA PATH IS INVISIBLE TO FRESHNESS (§5.2)
#        ADDED. Reason: §5.2 asks whether a real workflow the module makes harder than it
#        should be exists, and calls that a legitimate certification failure. This is the
#        one the traversals surfaced.
# ===========================================================================


@pytest.mark.asyncio
async def test_t20_a_symbol_fed_only_by_polling_is_permanently_stale() -> None:
    """SEQUENCE: subscribe -> poll successfully, repeatedly, with no tick ever arriving ->
    evaluate_freshness.

    PRECONDITIONS: a live subscription and a history source that answers every poll with a bar
      whose venue timestamp is CURRENT. No tick is delivered, which is Stage 0's measured shape:
      `reqTickByTickData` returns Err 10189 and the delayed stream is a separate grant.
    EXPECTED END STATE (determined by AMENDMENT 6): the two channels are reported SEPARATELY.
      The poll channel carries a real, current venue timestamp and NO measured lag, so it reads
      `CANNOT_MEASURE` — which is not `STALE`. The tick channel, on which nothing has arrived,
      reads `CANNOT_MEASURE` too. Nothing is reported stale.
    OBSERVABLE: `freshness(now, SYM)`'s per-channel states; `last_poll_recv_ts`,
      `last_bar_venue_ts` and `last_tick_venue_ts` read per writer.

    FINDING — §5.2 FIT FOR PURPOSE, **the collapse CLOSED IN ARC 023 (F21)**, the missing
    measurement still open and reported below.

    WHAT IT FOUND: `evaluate_freshness` read `last_tick_venue_ts` and nothing else, so a symbol
    fed entirely by successful polls had `excess_staleness_s` of `None` — CANNOT COMPUTE —
    which the adapter treated as STALE. The module's own GAP-D4 says *"THE POLL FALLBACK IS THE
    ONLY MARGIN-CLASS PATH"* and GAP-D1 records that the real-time tick stream does not exist on
    this account, so the path the adapter documents as the only one it has was the path its
    freshness derivation could not see. Under `nics_risk_subsystem_spec_v1.3.md` §6.4:373-374 a
    STALE verdict means *halt new entries AND flatten open*: a Limiter wired to this adapter at
    Stage 0, on the poll path, would have been permanently halted.

    THE ANSWER WAS NOT INVENTED HERE. It was issued as `docs/SPEC-AMENDMENTS.md` AMENDMENT 6
    (operator ruling, ARC 023): freshness is PER CHANNEL, the seam declares which channels are
    fresh and which are stale, and the consumer decides which channels it requires. The three
    rulings this traversal listed as undetermined were decided that way — `bar_start_venue_ts`
    IS the poll channel's freshness stamp, a poll-fed symbol is not exempt, and the two clocks
    do NOT combine into one.

    WHAT IS STILL OPEN, AND IT IS NOT A CODE DEFECT: the poll channel's `effective_lag_s` has
    never been measured on this system, so the channel reads `CANNOT_MEASURE` rather than
    `FRESH`. The tick channel's measured 600.0-601.9 s figure is NOT substituted for it — that
    would be AMENDMENT 3's substitution wearing a plausible number — and the adapter refuses the
    substitution structurally. KNOWN-RED, discharged by the tap in
    `~/nix/downloads/tap_session_runbook.md`; `broker_datafeed_ibkr.IB_POLL_LAG_RECORD` carries
    the marker.

    THE CONTROL IS THE OTHER ARM: the same adapter, same threshold, with ticks delivered, reads
    UP — so this is not "the traversal cannot make anything read UP".
    """
    now = 1000.0
    ad, sink, _ = await new_ad(history=lambda s: [bar_row(now - 1.0)])
    await ad.subscribe(SYM)
    for _ in range(3):
        await ad.poll_history(SYM)

    nonvac(
        [a.ok for a in ad.poll_attempts()] == [True, True, True],
        f"the polls did not succeed: {[(a.ok, a.error) for a in ad.poll_attempts()]}",
    )
    nonvac(
        len(sink.bars) == 1,
        "no bar was published, so the feed is not actually delivering",
    )
    nonvac(
        ad.last_poll_recv_ts(SYM) is not None,
        "the poll clock was never written — the poll path did not run",
    )

    # THE REPAIR: the poll channel is SEEN, carries the venue's own stamp, and its unanswerable
    # question reads as unanswerable rather than as a halt trigger.
    report = ad.freshness(now, SYM)[0]
    assert report.observed_channels == (FeedChannel.TICK, FeedChannel.POLL)
    assert ad._symbols[SYM].last_tick_venue_ts is None
    assert ad.last_bar_venue_ts(SYM) == now - 1.0
    poll = report.channel(FeedChannel.POLL)
    assert poll is not None and poll.venue_ts == now - 1.0
    assert report.stale_channels == ()
    assert set(report.cannot_measure_channels) == {FeedChannel.TICK, FeedChannel.POLL}
    # THE RESIDUAL, asserted so it cannot be closed silently: the poll channel is unmeasured,
    # and the tick channel's figure has not been borrowed for it.
    assert poll.lag.declared_lag_s is None
    assert poll.lag.provenance is LagProvenance.UNOBSERVED
    # And the §2A:92 single-state summary still fails closed while nothing is fresh.
    assert ad.evaluate_freshness(now=now, symbol=SYM) is FeedState.STALE

    # THE CONTROL: one tick, same adapter, same threshold — UP. The traversal can reach UP.
    ad._on_ib_tick(SYM, 1.0, 1.0, now - 600.2, recv_ts=now)
    assert ad.evaluate_freshness(now=now, symbol=SYM) is FeedState.UP


@pytest.mark.asyncio
async def test_t20b_freshness_is_derived_for_a_symbol_the_adapter_has_never_heard_of() -> (
    None
):
    """SEQUENCE: `evaluate_freshness(now, symbol=<never subscribed, never polled>)`.

    PRECONDITIONS: a live session with NO subscriptions at all.
    EXPECTED END STATE: undetermined. Observed: the adapter publishes `on_feed_status(STALE,
      <symbol>)` — a health verdict about a symbol it has no relationship with — and the reason
      string says it was *"derived from excess staleness over 1 symbol(s)"*, which is a claim
      about a measurement that had no inputs.
    OBSERVABLE: the returned `FeedState` and the sink's last `feed_statuses` entry.

    FINDING — WORKING AS INTENDED, BUT SURPRISING, and the surprise has a spec-annotated
    consequence. STALE for an unknown symbol is fail-closed and defensible (CLAUDE.md directive
    4), and `evaluate_freshness`'s docstring commits to it: *"`None` (cannot compute) is treated
    as STALE."* What is surprising is the EMISSION. `nics_risk_subsystem_spec_v1.3.md` §2A:92
    annotates `on_feed_status` as the event that *"drives the stale=>halt+flatten path"*, so
    publishing STALE for a symbol nobody subscribed hands a consumer a halt-and-flatten trigger
    for an instrument this library has no relationship with — and §6.4:373-374 is where that
    ends. The verdict itself is right; broadcasting it is the part nothing asked for.

    debug.md §7.9 would put this in the CANNOT MEASURE column rather than the FAIL column, and
    `FeedState` has no member for that distinction — the same missing member T8 needs for a mode
    change, which is why the two findings should be triaged together rather than separately.
    """
    ad, sink, _ = await new_ad()
    nonvac(ad._symbols == {}, "the adapter already knows a symbol — arm is not clean")
    before = len(sink.feed_statuses)

    assert ad.evaluate_freshness(now=1.0, symbol="ZZZZ") is FeedState.STALE
    assert len(sink.feed_statuses) == before + 1
    state, symbol, reason = sink.feed_statuses[-1]
    assert (state, symbol) == (FeedState.STALE, "ZZZZ")
    # ARC 023: the reason is now the PER-CHANNEL summary, and the finding sharpens rather than
    # closes. The old text claimed the verdict was "derived from excess staleness over 1
    # symbol(s)" — a claim about a measurement that had no inputs. The new text names the empty
    # channel set, so the STALE is visibly an absence of evidence; the EMISSION, which is what
    # this traversal reports, is unchanged.
    assert "fresh=[] stale=[] cannot_measure=[]" in reason
    assert ad.freshness(1.0, "ZZZZ")[0].observed_channels == ()
    # And the symbol is still unknown afterwards — the verdict created no record to justify it.
    assert ad._symbols == {}
