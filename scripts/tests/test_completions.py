"""ARC 046 — the §2A exec-report parse and the §4:214 dedup, as units.

`check_limiter_daemon_dispatch` proves the RUNNING daemon dispatches a cancel
and deduplicates a re-delivery. It cannot reach the parse's fail-closed edges:
a completion the parse REFUSES never reaches the loop's dispatch, so the gate's
arms are silent on exactly the branches that decide whether an un-keyable exec
report is absorbed or named. Those branches are the subject here.

**EVERY CONTROL ASSERTS THE REASON** (check contract v2 §11): `MalformedCompletion`
is one exception type shared by six refusals, so a control keyed on the type
alone would pass whenever the parse refused for any reason at all.
"""
# pylint: disable=invalid-name,duplicate-code

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from nixrisk.completions import (  # pylint: disable=wrong-import-position
    COMPLETION_SCHEMA,
    SPEC_EVENTS,
    WIRED_EVENTS,
    CompletionDispatcher,
    Disposition,
    ExecReportDedup,
    MalformedCompletion,
    parse_completion,
)


def _blob(**fields: object) -> bytes:
    payload = {"schema": COMPLETION_SCHEMA, **fields}
    return json.dumps(payload).encode()


def _cancel(**over: object) -> bytes:
    base: dict[str, object] = {
        "event": "on_cancel",
        "client_order_id": "COID-1",
        "exec_id": "EXEC-1",
        "done_qty": 0,
    }
    base.update(over)
    return _blob(**base)


class _Outcomes:  # pylint: disable=too-few-public-methods
    """A stand-in for `OrderOutcomes`, recording what it was ASKED to do."""

    def __init__(self, released: float = 500.0) -> None:
        self.released = released
        self.calls: list[tuple[str, str]] = []
        #: ARC 053. Which VERB was asked for, per call. `calls` alone cannot say,
        #: and with two release verbs on the port that is the whole question: a
        #: dispatcher that routed a reject into `on_cancel` would leave `calls`
        #: identical. mypy found the missing verb before this stub did — the
        #: protocol grew and a stand-in that does not grow with it stops standing
        #: in for the thing under test.
        self.verbs: list[str] = []

    def on_cancel(self, client_order_id: str, *, reason: str = ""):
        """Record the call and return a released_margin the dispatcher reads."""
        self.calls.append((client_order_id, reason))
        self.verbs.append("on_cancel")
        return type("Rec", (), {"released_margin": self.released})()

    def on_reject(self, client_order_id: str, *, reason: str = ""):
        """ARC 053. §3's reject release, recorded separately from the cancel."""
        self.calls.append((client_order_id, reason))
        self.verbs.append("on_reject")
        return type("Rec", (), {"released_margin": self.released})()


# ---------------------------------------------------------------------------
# THE PARSE — every refusal names its own reason.
# ---------------------------------------------------------------------------
def test_a_WELL_FORMED_cancel_parses_and_keeps_its_PROVENANCE():
    """A well-formed §2A cancel parses into its fields, including where it came from."""
    c = parse_completion(_cancel(), source="/tmp/x/cancel.json")  # nosec B108
    assert c.event == "on_cancel"
    assert c.client_order_id == "COID-1"
    assert c.exec_id == "EXEC-1"
    assert c.source == "/tmp/x/cancel.json"  # nosec B108 - a label, not a path
    assert c.dedup_key == ("COID-1", "EXEC-1")


def test_an_exec_report_with_NO_EXEC_ID_is_REFUSED_and_names_4_214():
    """FAIL CLOSED: an event that cannot be keyed cannot be made idempotent."""
    with pytest.raises(MalformedCompletion) as exc:
        parse_completion(_cancel(exec_id=""), source="s")
    assert "no exec_id" in str(exc.value)
    assert "§4:214" in str(exc.value)
    assert "re-delivery would release twice" in str(exc.value)


def test_an_exec_report_with_NO_CLIENT_ORDER_ID_is_REFUSED_and_says_which():
    """FAIL CLOSED: an exec report with no client_order_id is refused, naming the field."""
    with pytest.raises(MalformedCompletion) as exc:
        parse_completion(_cancel(client_order_id=""), source="s")
    assert "carries no client_order_id" in str(exc.value)


def test_a_WRONG_SCHEMA_is_REFUSED_rather_than_read_into_a_meaning():
    """A schema this parser doesn't recognize is refused rather than guessed at."""
    with pytest.raises(MalformedCompletion) as exc:
        parse_completion(json.dumps({"schema": 99, "event": "on_cancel"}), source="s")
    assert "schema 99" in str(exc.value)
    assert "may not have" in str(exc.value)


def test_NON_JSON_and_a_NON_OBJECT_are_two_DIFFERENT_refusals():
    """Malformed JSON and valid-JSON-but-not-an-object are refused with distinct reasons."""
    with pytest.raises(MalformedCompletion) as first:
        parse_completion(b"{not json", source="s")
    with pytest.raises(MalformedCompletion) as second:
        parse_completion(b"[1, 2, 3]", source="s")
    assert "not JSON" in str(first.value)
    assert "not an object" in str(second.value)


def test_an_UNNAMED_event_is_REFUSED_and_lists_the_2A_set():
    """An exec report naming no event is refused, and the refusal lists §2A's event set."""
    with pytest.raises(MalformedCompletion) as exc:
        parse_completion(_cancel(event=""), source="s")
    assert "names no event" in str(exc.value)
    assert "on_fill" in str(exc.value)


# ---------------------------------------------------------------------------
# THE DEDUP — §4:214's key is the PAIR, and the ceiling is honest about itself.
# ---------------------------------------------------------------------------
def test_the_KEY_is_the_PAIR_so_a_SECOND_exec_report_for_ONE_ORDER_is_NOT_a_duplicate():
    """§4's fill-then-remainder-cancel race is EXPECTED, not a re-delivery."""
    dedup = ExecReportDedup()
    assert dedup.claim(("COID-1", "EXEC-1")) is True
    assert dedup.claim(("COID-1", "EXEC-2")) is True, (
        "a distinct exec report for the same order was deduped away — §4:214 "
        "keys on the pair precisely so the remainder cancel still arrives"
    )
    assert dedup.claim(("COID-1", "EXEC-1")) is False


def test_the_CEILING_EVICTS_FIFO_and_COUNTS_it_rather_than_claiming_it_never_happens():
    """The dedup ring evicts its oldest key at capacity and counts the eviction
    rather than pretending it never happened."""
    dedup = ExecReportDedup(max_keys=2)
    dedup.claim(("o", "a"))
    dedup.claim(("o", "b"))
    assert dedup.evicted == 0
    dedup.claim(("o", "c"))
    assert dedup.evicted == 1
    assert dedup.seen(("o", "a")) is False, "the OLDEST key should have gone"
    assert dedup.seen(("o", "c")) is True


def test_a_dedup_with_NO_CAPACITY_is_REFUSED_at_construction():
    """A dedup ring with zero capacity is refused at construction — it would
    deduplicate nothing."""
    with pytest.raises(Exception) as exc:
        ExecReportDedup(max_keys=0)
    assert "deduplicates nothing" in str(exc.value)


# ---------------------------------------------------------------------------
# THE DISPATCH — five dispositions, never a boolean.
# ---------------------------------------------------------------------------
def test_a_CANCEL_reaches_the_PROVEN_handler_and_reports_what_it_RELEASED():
    """A cancel dispatches to the real handler and reports exactly what it released."""
    outcomes = _Outcomes(released=2000.0)
    d = CompletionDispatcher(outcomes)
    result = d.dispatch(parse_completion(_cancel(), source="s"))
    assert result.disposition == Disposition.DISPATCHED
    assert result.released_margin == 2000.0
    assert d.ledger.dispatched == 1
    assert outcomes.calls[0][0] == "COID-1"
    assert "§5:322's loop dispatched it serially" in outcomes.calls[0][1]


def test_a_HANDLER_THAT_RELEASED_NOTHING_is_REFUSED_and_never_counted_DISPATCHED():
    """§7.12 #2: a bare `dispatched` counter over a handler that did nothing."""
    outcomes = _Outcomes(released=0.0)
    d = CompletionDispatcher(outcomes)
    result = d.dispatch(parse_completion(_cancel(), source="s"))
    assert result.disposition == Disposition.REFUSED
    assert d.ledger.dispatched == 0
    assert d.ledger.refused == 1
    assert "released no margin" in result.reason


def test_a_REDELIVERY_is_a_DUPLICATE_and_the_HANDLER_IS_NEVER_CALLED_TWICE():
    """A re-delivered exec report is recorded as a duplicate and the handler
    runs exactly once."""
    outcomes = _Outcomes()
    d = CompletionDispatcher(outcomes)
    blob = _cancel()
    d.dispatch(parse_completion(blob, source="s"))
    result = d.dispatch(parse_completion(blob, source="s"))
    assert result.disposition == Disposition.DUPLICATE
    assert len(outcomes.calls) == 1, "§3's handler ran twice for one exec report"
    assert d.ledger.duplicates == 1
    assert "§14 forbids" in result.reason


# A LITERAL list, not a comprehension over SPEC_EVENTS. `check_derived_claims`
# counts this suite's tests by AST and REFUSES to trust a parametrize whose
# argvalues it cannot evaluate statically — measured this arc, where the
# comprehension turned that claim into "NOT MEASURED". The literal is kept
# honest by the assertion below it: if SPEC_EVENTS or WIRED_EVENTS moves and
# this list does not, the test says so by name.
@pytest.mark.parametrize(
    "event",
    [
        "on_ack",
        "on_balance",
        "on_margin",
        "on_position",
        "on_session",
    ],
)
def test_every_UNWIRED_2A_event_is_RECORDED_as_unwired_and_NAMES_ITSELF(event: str):
    """An unwired path that is silently dropped reads exactly like one that works."""
    # ARC 047 wired `on_fill`, so it LEFT this set; ARC 053 wired `on_reject`
    # and it left too. The literal moving is the mechanism WORKING: the
    # assertion below named the drift the moment `WIRED_EVENTS` grew — it went
    # red in ARC 053's own runtime gate, before the arc's first commit — which
    # is exactly what a literal list is kept for. A comprehension here would
    # have adjusted silently and this test would have gone on reporting that it
    # measured the unwired set while measuring a smaller one.
    assert set(SPEC_EVENTS) - set(WIRED_EVENTS) == {
        "on_ack",
        "on_balance",
        "on_margin",
        "on_position",
        "on_session",
    }, (
        "the §2A event set or WIRED_EVENTS moved and this test's literal "
        "parameter list did not — the unwired set is no longer what is measured"
    )
    outcomes = _Outcomes()
    d = CompletionDispatcher(outcomes)
    result = d.dispatch(
        parse_completion(_cancel(event=event, exec_id=f"E-{event}"), source="s")
    )
    assert result.disposition == Disposition.UNWIRED
    assert event in result.reason
    assert "is UNCHANGED and this is recorded, not absorbed" in result.reason
    assert not outcomes.calls


def test_an_event_OUTSIDE_2A_is_UNKNOWN_which_is_NOT_the_same_as_UNWIRED():
    """An event outside the §2A set is UNKNOWN, distinct from an unwired §2A event."""
    outcomes = _Outcomes()
    d = CompletionDispatcher(outcomes)
    result = d.dispatch(parse_completion(_cancel(event="on_teleport"), source="s"))
    assert result.disposition == Disposition.UNKNOWN
    assert d.ledger.unwired == 0
    assert "not one of §2A:74-84's pushed events" in result.reason


def test_the_DEDUP_IS_CLAIMED_BEFORE_the_handler_so_a_RAISING_handler_cannot_double():
    """A post-hoc claim would leave the key unclaimed on the error path."""

    class _Raises:  # pylint: disable=too-few-public-methods
        def __init__(self) -> None:
            self.calls = 0

        def on_cancel(  # pylint: disable=unused-argument
            self, client_order_id: str, *, reason: str = ""
        ):
            """Count the call, then raise — proves the dedup claim survives a
            handler that blows up."""
            self.calls += 1
            raise RuntimeError("the handler blew up")

    outcomes = _Raises()
    d = CompletionDispatcher(outcomes)
    blob = _cancel()
    with pytest.raises(RuntimeError):
        d.dispatch(parse_completion(blob, source="s"))
    result = d.dispatch(parse_completion(blob, source="s"))
    assert result.disposition == Disposition.DUPLICATE
    assert outcomes.calls == 1


def test_the_RECORD_carries_the_PROVENANCE_a_reader_outside_the_process_needs():
    """§7.12 #4: `last_source` is what separates the daemon from a direct call."""
    d = CompletionDispatcher(_Outcomes())
    src = "/tmp/rt/completions/c1.json"  # nosec B108 - a label, not a path
    d.dispatch(parse_completion(_cancel(), source=src))
    record = d.record()
    assert record["last_source"] == src
    assert record["last_disposition"] == Disposition.DISPATCHED
    assert record["last_event"] == "on_cancel"
    assert record["wired_events"] == list(WIRED_EVENTS)
    assert record["consumed"] == 0, (
        "`consumed` is stamped by the LOOP's handler, not by the dispatcher — "
        "if the dispatcher moved it, removing the dispatch would also remove "
        "the evidence that a completion ever arrived"
    )


# ===========================================================================
# ARC 047 — THE FILL PATH. Wired as a SECOND port, because §3's *converts to
# open-margin* is a cascade and `OrderOutcomes` has no `on_fill` to reuse.
# ===========================================================================
def _fill(**over: object) -> bytes:
    base: dict[str, object] = {
        "event": "on_fill",
        "client_order_id": "COID-F",
        "exec_id": "EXEC-F",
        "done_qty": 3,
        "symbol": "ES",
        "price": 5000.0,
        "cumulative_qty": 3,
    }
    base.update(over)
    return _blob(**base)


class _Sink:
    """A stand-in for `LimiterFillSink`, recording what the dispatcher asked it.

    Returns a `FillOutcome`-shaped object rather than a real one: the subject
    here is the DISPATCHER's routing and its safety re-assertion, and a real
    cascade would make every assertion below a statement about `fills.py`.
    `checks/check_limiter_daemon_dispatch.py` drives the real one, in a real
    daemon, which is the measurement this cannot make and must not imitate.
    """

    def __init__(self, *, arm_level: float = 4998.0, open_margin: float = 2100.0):
        self.calls: list[tuple[object, ...]] = []
        self._arm_level = arm_level
        self._open_margin = open_margin
        self._outcomes: list[object] = []

    # R0913/R0917: the six positional fields ARE §2A:75's `on_fill` signature,
    # transcribed. A stand-in that took a struct would not satisfy the port it
    # exists to stand in for.
    def on_fill(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self, coid, exec_id, symbol, filled_qty, price, cumulative_qty
    ):
        """Record the six §2A fields and produce one outcome."""
        self.calls.append((coid, exec_id, symbol, filled_qty, price, cumulative_qty))
        armed = (
            None
            if self._arm_level <= 0.0
            else type(
                "S",
                (),
                {
                    "level": self._arm_level,
                    "initial_distance_ticks": 8,
                    "mode": type("M", (), {"value": "fixed"})(),
                },
            )()
        )
        row = type("R", (), {"size": filled_qty})()
        origin = type("O", (), {"trade_id": "TRD-1"})()
        picture = type("P", (), {"sum_open_margin": self._open_margin})()
        write = type("W", (), {"row": row, "origin": origin, "picture": picture})()
        self._outcomes.append(
            type("FO", (), {"armed": armed, "write": write, "sum_reservations": 0.0})()
        )

    def outcomes(self):
        """Every outcome produced, in arrival order."""
        return tuple(self._outcomes)


def test_on_fill_is_WIRED_and_is_ROUTED_TO_THE_FILL_SINK_not_to_outcomes():
    """`on_fill` reaches the fill sink; §3's cancel handler is never called.

    The two ports are not interchangeable: one releases, one CONVERTS.
    """
    outcomes, sink = _Outcomes(), _Sink()
    d = CompletionDispatcher(outcomes, fills=sink)
    result = d.dispatch(parse_completion(_fill(), source="s"))
    assert result.disposition == Disposition.DISPATCHED, result.reason
    assert sink.calls == [("COID-F", "EXEC-F", "ES", 3, 5000.0, 3)]
    assert not outcomes.calls, "a fill reached §3's CANCEL handler"
    assert d.ledger.fills_dispatched == 1
    assert d.ledger.cancels_dispatched == 0
    assert result.trade_id == "TRD-1"
    assert result.stop_level == 4998.0
    assert result.converted_margin == 2100.0
    assert result.opened_size == 3


def test_a_fill_that_CONVERTED_WITHOUT_AN_ARMED_STOP_is_REFUSED_and_NAMES_IT():
    """§7.12 guard 6 — the daemon-boundary safety re-assertion.

    `fills.py` already makes this unreachable by arming first and raising on
    refusal. It is asserted a SECOND time here because the cost of the
    redundancy is one comparison and the cost of being wrong is a live position
    nothing protects.
    """
    d = CompletionDispatcher(_Outcomes(), fills=_Sink(arm_level=0.0))
    result = d.dispatch(parse_completion(_fill(), source="s"))
    assert result.disposition == Disposition.REFUSED, result.reason
    assert "UNPROTECTED POSITION" in result.reason
    assert "§14 resolves that toward FLAT" in result.reason
    assert d.ledger.fills_dispatched == 0
    assert d.ledger.opened == 0


def test_a_fill_whose_CASCADE_RAISES_is_CONTAINED_as_a_REFUSAL_carrying_the_reason():
    """A raising cascade must not kill the tick, and must not be absorbed either."""

    class _Raises:
        """A sink whose cascade refuses — `UntradableSymbol`'s shape."""

        def on_fill(self, *args):  # pylint: disable=unused-argument
            """Raise the way `fills.py` does: loudly, naming the condition."""
            raise RuntimeError("symbol 'NQ' has no positive tick size")

        def outcomes(self):
            """No outcome was produced."""
            return ()

    d = CompletionDispatcher(_Outcomes(), fills=_Raises())
    result = d.dispatch(parse_completion(_fill(), source="s"))
    assert result.disposition == Disposition.REFUSED
    assert "fill cascade REFUSED" in result.reason
    assert "no positive tick size" in result.reason, (
        "the REASON is the assertion (check contract v2 rule 11); a refusal "
        "that dropped the cascade's own sentence would leave an operator with "
        "a disposition and no condition"
    )


def test_a_fill_with_NO_SINK_is_a_NAMED_REFUSAL_not_an_unwired_event():
    """*This build has no fill sink* and *this build does not wire fill* are two
    readings, and `WIRED_EVENTS` already claims the second is false."""
    d = CompletionDispatcher(_Outcomes())
    result = d.dispatch(parse_completion(_fill(), source="s"))
    assert result.disposition == Disposition.REFUSED
    assert "constructed with no fill sink" in result.reason
    assert d.ledger.unwired == 0
    assert d.record()["fill_sink"] is False


def test_a_REDELIVERED_fill_is_DEDUPED_at_the_daemon_boundary_and_never_reaches_the_cascade():
    """§4:214: one exec report delivered twice runs the cascade ONCE.

    The fill is where a defeated dedup costs most — a second dispatch re-runs an
    arm, a release AND a published row.
    """
    sink = _Sink()
    d = CompletionDispatcher(_Outcomes(), fills=sink)
    first = d.dispatch(parse_completion(_fill(), source="s"))
    second = d.dispatch(parse_completion(_fill(), source="s"))
    assert first.disposition == Disposition.DISPATCHED
    assert second.disposition == Disposition.DUPLICATE
    assert len(sink.calls) == 1, "§4's cascade ran twice for one exec report"
    assert d.ledger.fills_dispatched == 1
    assert d.ledger.duplicates == 1


@pytest.mark.parametrize(
    ("field", "value", "needle"),
    [
        ("symbol", "", "names no symbol"),
        ("price", "not-a-number", "non-numeric price"),
        ("price", 0.0, "not a positive finite number"),
        ("done_qty", 0, "is not a confirmation"),
        ("cumulative_qty", 1, "BELOW this execution's done_qty"),
    ],
)
def test_a_FILL_MISSING_A_FIELD_4_NEEDS_is_REFUSED_AT_THE_PARSE_and_says_which(
    field: str, value: object, needle: str
):
    """Fail closed at the parse, BEFORE §4:214's key is claimed.

    A fill that reached the cascade missing one of these would fail deep — after
    the dedup key was claimed, which is the one place a refusal cannot be
    retried (§4:240-241 forbids the resend).
    """
    with pytest.raises(MalformedCompletion) as exc:
        parse_completion(_fill(**{field: value}), source="s")
    assert needle in str(exc.value)


def test_a_NON_FILL_event_carries_NO_price_and_that_is_not_a_missing_value():
    """§2A's `on_cancel` genuinely has no symbol, price or running total."""
    c = parse_completion(_cancel(), source="s")
    assert (c.symbol, c.price, c.cumulative_qty) == ("", 0.0, 0)


# ---------------------------------------------------------------------------
# ARC 053 — the REJECT route. §3 has two non-fill release verbs and the
# dispatcher must call the RIGHT one: a reject routed into `on_cancel` releases
# the same margin and books the wrong §3 terminal path, which §11.7's reconcile
# and every §12.10 row downstream then carry as a fact.
# ---------------------------------------------------------------------------
def test_a_2A_on_reject_is_routed_to_ON_REJECT_and_not_to_on_cancel():
    """The verb, not just the release. Both release; only one is correct."""
    outcomes = _Outcomes(released=750.0)
    d = CompletionDispatcher(outcomes)
    result = d.dispatch(
        parse_completion(_cancel(event="on_reject", exec_id="E-REJ"), source="s")
    )
    assert result.disposition == Disposition.DISPATCHED, result.reason
    assert outcomes.verbs == ["on_reject"], outcomes.verbs
    assert result.released_margin == 750.0
    # The reason names the §2A event and the §5:322 path it came through.
    assert "on_reject" in result.reason
    assert "the venue refused the order outright" in result.reason


def test_the_LEDGER_counts_a_reject_SEPARATELY_from_a_cancel():
    """§7.12 guard 1. `_finish` counted every non-fill dispatch as a cancel until
    ARC 053; the moment `on_reject` was wired that would have made a reject
    indistinguishable from a cancel in the one record an out-of-process reader
    opens."""
    outcomes = _Outcomes()
    d = CompletionDispatcher(outcomes)
    d.dispatch(parse_completion(_cancel(exec_id="E-C"), source="s"))
    d.dispatch(parse_completion(_cancel(event="on_reject", exec_id="E-R"), source="s"))
    record = d.record()
    assert record["cancels_dispatched"] == 1, record
    assert record["rejects_dispatched"] == 1, record
    assert record["dispatched"] == 2, record


def test_a_reject_whose_LEDGER_REFUSES_is_REFUSED_and_never_counted_dispatched():
    """A handler that ran and released nothing is not a dispatch (§7.12 guard 2)."""
    outcomes = _Outcomes(released=0.0)
    d = CompletionDispatcher(outcomes)
    result = d.dispatch(
        parse_completion(_cancel(event="on_reject", exec_id="E-R0"), source="s")
    )
    assert result.disposition == Disposition.REFUSED, result.reason
    assert "released no margin" in result.reason
    assert d.record()["rejects_dispatched"] == 0
