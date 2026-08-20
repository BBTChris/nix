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

    def on_cancel(self, client_order_id: str, *, reason: str = ""):
        """Record the call and return a released_margin the dispatcher reads."""
        self.calls.append((client_order_id, reason))
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
        "on_fill",
        "on_reject",
        "on_balance",
        "on_margin",
        "on_position",
        "on_session",
    ],
)
def test_every_UNWIRED_2A_event_is_RECORDED_as_unwired_and_NAMES_ITSELF(event: str):
    """An unwired path that is silently dropped reads exactly like one that works."""
    assert set(SPEC_EVENTS) - set(WIRED_EVENTS) == {
        "on_ack",
        "on_fill",
        "on_reject",
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
