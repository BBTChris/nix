"""ARC 037 / sub-agent C — §4:274's quarantine, driven ACROSS A PROCESS BOUNDARY.

The can-fail suite for `nixrisk.supervision.QuarantineLedger` and for the two
`CrashLoopBreaker` properties CHECK-DEBT D3.250 and D3.251 measured missing:

* **D3.250** — three restarts fsynced, `is_quarantined -> True` on the breaker
  that counted them, and a SECOND breaker over the SAME ledger (which is exactly
  what the next supervision process constructs at boot) answering
  `is_quarantined -> False` while `restarts_in_window` still returned 3 at a cap
  of 3. §4:274 is *"Quarantine is NOT auto-resurrected; return is
  operator-driven"*, and a supervisor restart was doing the resurrecting.
* **D3.251** — the §12.11:779 restore FLOOR lived in process memory, so a
  restart un-did the operator's restore and re-quarantined the strategy on
  restarts it had already been forgiven for.

Every `§` cites `docs/nics_risk_subsystem_spec_v1.3.md` unless another document
is named on the same line.

THE §0a HAZARDS, TREATED AS HYPOTHESES AND MEASURED

* **the book is written and never queried.** So the reconstruction is driven in a
  REAL SUBPROCESS — a fresh interpreter — and not only through a second object
  in this one, which a module-level cache would satisfy.
* **the refusal reason still contradicts the ledger.** So every control asserts
  the REASON, and the numbers it must carry are read from the ledger FILE by this
  suite, not from the object under test.
* **the gate is green because nothing was ever quarantined.** So the same book
  path is read BEFORE the record exists and must answer NOT-quarantined; and the
  falsifier `_VolatileBreaker` — a breaker that keeps the verdict in memory, i.e.
  the tree as ARC 036 measured it — is shown to LOSE the property in the same
  drive where the real one keeps it.
* **a restore that DELETED the quarantine would also "change the answer".** So
  the restore controls assert BOTH records remain on disk and assert the exact
  post-restore count, never merely that it moved.
"""

# pylint: disable=invalid-name,redefined-outer-name,protected-access
# pylint: disable=missing-function-docstring,too-few-public-methods
# pylint: disable=missing-class-docstring,import-outside-toplevel
# invalid-name: the test names are sentences. protected-access: the falsifier
# replaces the breaker's own fold to build a WRONG variant — that is how a
# falsifier is written.

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

# pylint: disable=wrong-import-position
import risk_config
from nixrisk.supervision import (
    QUARANTINE_KIND,
    QUARANTINE_LEDGER_SUFFIX,
    RESTORE_KIND,
    BreakerScope,
    CrashLoopBreaker,
    QuarantineLedger,
    QuarantineState,
    RestartLedger,
    SupervisionKnobs,
    SupervisionUsageError,
)


class Alerts:
    def __init__(self) -> None:
        self.raised: list[tuple[str, str]] = []

    def alert(self, code: str, message: str) -> None:
        self.raised.append((code, message))

    def codes(self) -> list[str]:
        return [code for code, _ in self.raised]


class Plane2:
    def __init__(self) -> None:
        self.lines: list[tuple[str, dict]] = []

    def emit(self, event: str, **fields) -> str:
        self.lines.append((event, dict(fields)))
        return event


class _VolatileBreaker(CrashLoopBreaker):
    """THE FALSIFIER: the tree as ARC 036 MEASURED it.

    It writes the book and then refuses to read it back at construction, which is
    the plain in-process `dict` D3.250 names. Every control that asserts the real
    breaker SURVIVES a reconstruction also drives this one and requires it to
    LOSE the property, so the assertion is proven able to fail.
    """

    def __init__(self, **kwargs) -> None:
        ledger = kwargs["ledger"]
        book = kwargs.get("quarantine_ledger") or QuarantineLedger.beside(ledger)
        real = book.state
        empty = QuarantineState(live={}, floors={}, records_read=0)
        book.state = lambda: empty  # type: ignore[method-assign]
        try:
            super().__init__(**{**kwargs, "quarantine_ledger": book})
        finally:
            book.state = real  # type: ignore[method-assign]


@pytest.fixture
def knobs() -> SupervisionKnobs:
    """The SHIPPED §12A knobs, read from `risks/supervision.config.json`."""
    loaded = risk_config.load_risk_configs(REPO)
    return SupervisionKnobs.from_config(loaded.modules["supervision"].values)


def _breaker(path: Path, knobs: SupervisionKnobs, *, cls=CrashLoopBreaker):
    """ONE fresh breaker over `path` — what supervision constructs at boot."""
    alerts, plane2 = Alerts(), Plane2()
    breaker = cls(
        knobs=knobs,
        scope=BreakerScope.STRATEGY,
        ledger=RestartLedger(path),
        alert=alerts,
        plane2=plane2,
    )
    return breaker, alerts, plane2


def _crash_to_the_cap(
    path: Path, knobs: SupervisionKnobs, base: float, *, cls=CrashLoopBreaker
):
    breaker, alerts, plane2 = _breaker(path, knobs, cls=cls)
    verdict = None
    for i in range(knobs.crash_loop_max):
        verdict = breaker.record_restart("alpha", now=base + i)
    return breaker, alerts, plane2, verdict


# ==========================================================================
# The book itself
# ==========================================================================


def test_the_QUARANTINE_BOOK_is_append_only_0600_and_holds_TWO_KINDS(
    tmp_path: Path,
) -> None:
    """Seam freeze (c): two record kinds and no more, one fsync per record."""
    book = QuarantineLedger(tmp_path / "q.jsonl")
    first = book.record_quarantine(
        "alpha", 100.0, reason="because", restarts_in_window=3, cap=3, window_s=600.0
    )
    second = book.record_restore("alpha", 200.0, operator="bbt", counter_floor=150.0)

    assert (first.seq, second.seq) == (1, 2)
    assert book.path.stat().st_mode & 0o777 == 0o600, oct(book.path.stat().st_mode)
    rows = [
        json.loads(ln)
        for ln in book.path.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    assert [row["kind"] for row in rows] == [QUARANTINE_KIND, RESTORE_KIND]
    assert rows[0]["restarts_in_window"] == 3 and rows[0]["cap"] == 3
    assert rows[1]["operator"] == "bbt" and rows[1]["counter_floor"] == 150.0


def test_a_RESTORE_SUPERSEDES_by_APPENDING_and_never_by_DELETING(
    tmp_path: Path,
) -> None:
    """Directive 6. The operator's return is itself banked evidence: a book that
    erased the quarantine to express the restore would leave the operator's act
    with no record anywhere on disk."""
    book = QuarantineLedger(tmp_path / "q.jsonl")
    book.record_quarantine(
        "alpha", 100.0, reason="r", restarts_in_window=3, cap=3, window_s=600.0
    )
    before = book.path.read_text(encoding="utf-8")

    book.record_restore("alpha", 200.0, operator="bbt", counter_floor=150.0)

    after = book.path.read_text(encoding="utf-8")
    assert after.startswith(before), "the quarantine record was REWRITTEN"
    state = book.state()
    assert state.live == {}, state.live
    assert state.floors == {"alpha": 150.0}, state.floors
    assert state.records_read == 2


def test_a_DAMAGED_quarantine_line_is_REPORTED_and_never_silently_skipped(
    tmp_path: Path,
) -> None:
    """CAN-FAIL, planted on the book: a quarantine that was written and cannot be
    read is a resurrection the cap will not see, so skipping it fails OPEN."""
    book = QuarantineLedger(tmp_path / "q.jsonl")
    book.record_quarantine(
        "alpha", 100.0, reason="r", restarts_in_window=3, cap=3, window_s=600.0
    )
    with book.path.open("a", encoding="utf-8") as handle:
        handle.write('{"kind":"quarantine","subject":"beta"}\n')

    with pytest.raises(SupervisionUsageError) as caught:
        book.state()

    assert "is not a quarantine record" in str(caught.value)
    assert "a resurrection the cap will not see" in str(caught.value)
    assert f"{book.path}:2" in str(caught.value)


def test_an_UNKNOWN_record_KIND_is_REFUSED_rather_than_folded_as_something_else(
    tmp_path: Path,
) -> None:
    """CAN-FAIL: two kinds and no more. A third kind silently folded as neither
    would be a quarantine the fold cannot see."""
    book = QuarantineLedger(tmp_path / "q.jsonl")
    book.path.write_text(
        '{"kind":"amnesty","subject":"a","ts":1.0,"seq":1}\n', encoding="utf-8"
    )

    with pytest.raises(SupervisionUsageError) as caught:
        book.records()

    assert "neither 'quarantine' nor 'restore'" in str(caught.value)


def test_the_BOOK_defaults_BESIDE_the_restart_ledger_so_no_CALLER_changed(
    tmp_path: Path, knobs: SupervisionKnobs
) -> None:
    """Backwards compatibility is the reason the default is DERIVED: every
    existing `CrashLoopBreaker(...)` site keeps working, and two books describing
    one subject cannot be pointed at two directories by two callers."""
    ledger = tmp_path / "restarts.jsonl"
    breaker, _, _ = _breaker(ledger, knobs)
    assert breaker.quarantine_book.path == Path(str(ledger) + QUARANTINE_LEDGER_SUFFIX)


# ==========================================================================
# D3.250 — the VERDICT survives the breaker's reconstruction
# ==========================================================================


def test_the_QUARANTINE_survives_a_NEW_BREAKER_over_the_SAME_LEDGER(
    tmp_path: Path, knobs: SupervisionKnobs
) -> None:
    """§4:274 — 'Quarantine is NOT auto-resurrected; return is operator-driven'.

    A supervision restart IS a new breaker over the same on-disk state. D3.250
    measured this answering False while `restarts_in_window` still returned the
    cap.
    """
    path = tmp_path / "restarts.jsonl"
    _, alerts, _, verdict = _crash_to_the_cap(path, knobs, 1000.0)
    assert verdict is not None and verdict.quarantined, verdict
    assert "supervision.quarantine" in alerts.codes()

    reborn, _, _ = _breaker(path, knobs)

    assert reborn.is_quarantined("alpha"), (
        "a NEW breaker over the SAME fsynced ledger auto-resurrected the "
        "strategy — CHECK-DEBT D3.250"
    )
    rebuilt = reborn.quarantine_verdict("alpha")
    assert rebuilt is not None
    assert rebuilt.restarts_in_window == knobs.crash_loop_max
    assert rebuilt.cap == knobs.crash_loop_max
    assert rebuilt.tripped and rebuilt.quarantined and not rebuilt.halted
    assert "CRASH-LOOP CAP HIT" in rebuilt.reason


def test_the_FALSIFIER_a_MEMORY_ONLY_breaker_LOSES_the_property(
    tmp_path: Path, knobs: SupervisionKnobs
) -> None:
    """NON-VACUITY, and it is the tree as ARC 036 measured it.

    `_VolatileBreaker` writes the book and refuses to read it at construction.
    Driven through the SAME sequence it reproduces D3.250 exactly: not
    quarantined, while the restart ledger still holds the cap.
    """
    path = tmp_path / "restarts.jsonl"
    _crash_to_the_cap(path, knobs, 1000.0)

    volatile, _, _ = _breaker(path, knobs, cls=_VolatileBreaker)
    real, _, _ = _breaker(path, knobs)

    assert volatile.is_quarantined("alpha") is False
    assert len(volatile.restarts_in_window("alpha", 1005.0)) >= knobs.crash_loop_max
    allowed, why = volatile.may_relaunch("alpha")
    assert allowed is True, "the falsifier did not lose the property"
    assert real.is_quarantined("alpha") is True, why


def test_the_REFUSAL_REASON_QUOTES_the_BOOK_and_CANNOT_contradict_it(
    tmp_path: Path, knobs: SupervisionKnobs
) -> None:
    """D3.250's SECOND HALF. The old text read '… the §4:272 cap of 3 restart(s)
    per 10.0 min has not been reached' on an object whose ledger held three.

    The numbers asserted here are read out of the FILE by this test, not out of
    the breaker, so the two sources are independent (check contract v2 §11).
    """
    path = tmp_path / "restarts.jsonl"
    _crash_to_the_cap(path, knobs, 1000.0)
    reborn, _, _ = _breaker(path, knobs)

    allowed, why = reborn.may_relaunch("alpha")

    rows = [
        json.loads(ln)
        for ln in reborn.quarantine_book.path.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    record = [row for row in rows if row["kind"] == QUARANTINE_KIND][-1]
    assert allowed is False
    assert f"seq={record['seq']}" in why
    assert f"restarts_in_window={record['restarts_in_window']}" in why
    assert f"cap={record['cap']}" in why
    assert "quarantine-restore" in why
    assert "has not been reached" not in why, (
        "the refusal for a QUARANTINED subject repeats D3.250's false claim"
    )


def test_the_ALLOWED_reason_states_the_BOOK_FACT_rather_than_a_SECOND_CLAIM(
    tmp_path: Path, knobs: SupervisionKnobs
) -> None:
    """The allowed branch is where D3.250's false sentence lived. It now names
    the absence of a record — which is the SAME fact as the cap not being
    reached, read once — instead of asserting the cap independently."""
    breaker, _, _ = _breaker(tmp_path / "restarts.jsonl", knobs)
    breaker.record_restart("alpha", now=1000.0)

    allowed, why = breaker.may_relaunch("alpha")

    assert allowed is True
    assert str(breaker.quarantine_book.path) in why
    assert "NO live 'quarantine' record" in why


# ==========================================================================
# D3.251 — the §12.11:779 restore FLOOR survives too
# ==========================================================================


def test_the_RESTORE_FLOOR_survives_a_NEW_BREAKER_over_the_SAME_LEDGER(
    tmp_path: Path, knobs: SupervisionKnobs
) -> None:
    """§12.11:779 — the verb 'resets the crash-loop counter'. D3.251 measured the
    same breaker reporting 2 and a NEW one reporting 3, the pre-restore count.

    The floor is placed STRICTLY INSIDE the restart series so the expected
    post-restore count is a specific NON-ZERO number: a restore that DELETED
    records would also change the answer, and must not pass.
    """
    path = tmp_path / "restarts.jsonl"
    breaker, _, _, _ = _crash_to_the_cap(path, knobs, 1000.0)
    before = len(breaker.restarts_in_window("alpha", 1100.0))
    expected = knobs.crash_loop_max - 1

    breaker.restore("alpha", operator="bbt", now=1000.5)
    same_process = len(breaker.restarts_in_window("alpha", 1100.0))
    reborn, _, _ = _breaker(path, knobs)
    fresh = len(reborn.restarts_in_window("alpha", 1100.0))

    assert before == knobs.crash_loop_max
    assert same_process == expected, "the floor did not apply in-process"
    assert fresh == expected, (
        f"a NEW breaker reports {fresh} restart(s) after the operator's restore, "
        f"expected {expected}; {knobs.crash_loop_max} is CHECK-DEBT D3.251 (the "
        "floor never reached disk) and 0 would be a deletion directive 6 forbids"
    )
    assert reborn.is_quarantined("alpha") is False
    assert len(RestartLedger(path).records()) == knobs.crash_loop_max, (
        "restore DELETED restart records"
    )


def test_the_FALSIFIER_LOSES_the_RESTORE_FLOOR_and_reports_the_PRE_restore_count(
    tmp_path: Path, knobs: SupervisionKnobs
) -> None:
    """NON-VACUITY for the row above: `_VolatileBreaker` reproduces D3.251
    exactly — the pre-restore count, on a strategy the operator already cleared."""
    path = tmp_path / "restarts.jsonl"
    breaker, _, _, _ = _crash_to_the_cap(path, knobs, 1000.0)
    breaker.restore("alpha", operator="bbt", now=1000.5)

    volatile, _, _ = _breaker(path, knobs, cls=_VolatileBreaker)
    real, _, _ = _breaker(path, knobs)

    assert len(volatile.restarts_in_window("alpha", 1100.0)) == knobs.crash_loop_max
    assert len(real.restarts_in_window("alpha", 1100.0)) == knobs.crash_loop_max - 1


def test_a_RESTORED_strategy_that_crashes_AGAIN_re_quarantines_on_NEW_restarts(
    tmp_path: Path, knobs: SupervisionKnobs
) -> None:
    """The consequence D3.251 calls SILENT AND DELAYED: a restored strategy must
    be re-quarantined only by restarts the operator has NOT already forgiven."""
    path = tmp_path / "restarts.jsonl"
    breaker, _, _, _ = _crash_to_the_cap(path, knobs, 1000.0)
    breaker.restore("alpha", operator="bbt", now=1100.0)

    reborn, alerts, _ = _breaker(path, knobs)
    verdicts = [
        reborn.record_restart("alpha", now=1200.0 + i)
        for i in range(knobs.crash_loop_max)
    ]

    assert [v.restarts_in_window for v in verdicts] == list(
        range(1, knobs.crash_loop_max + 1)
    ), [v.reason for v in verdicts]
    assert not any(v.tripped for v in verdicts[:-1])
    assert verdicts[-1].tripped and verdicts[-1].quarantined
    assert alerts.codes()[-1] == "supervision.quarantine"


# ==========================================================================
# THE PROCESS BOUNDARY — a second object in ONE interpreter is not the subject
# ==========================================================================


_DRIVER = textwrap.dedent(
    """
    import json, os, sys
    from pathlib import Path
    sys.path.insert(0, sys.argv[1])
    import risk_config
    from nixrisk.supervision import (
        BreakerScope, CrashLoopBreaker, RestartLedger, SupervisionKnobs,
    )

    class A:
        def alert(self, code, message): pass

    class P:
        def emit(self, event, **fields): return event

    values = risk_config.load_risk_configs(Path(sys.argv[2])).modules["supervision"].values
    knobs = SupervisionKnobs.from_config(values)
    b = CrashLoopBreaker(
        knobs=knobs, scope=BreakerScope.STRATEGY,
        ledger=RestartLedger(sys.argv[3]), alert=A(), plane2=P(),
    )
    verb, now = sys.argv[4], float(sys.argv[5])
    if verb == "crash":
        for i in range(knobs.crash_loop_max):
            b.record_restart("alpha", now=now + i)
    elif verb == "restore":
        b.restore("alpha", "bbt", now=now)
    allowed, why = b.may_relaunch("alpha")
    print(json.dumps({
        "pid": os.getpid(),
        "is_quarantined": b.is_quarantined("alpha"),
        "may_relaunch": allowed,
        "reason": why,
        "restarts_in_window": len(b.restarts_in_window("alpha", now + 100.0)),
    }))
    """
)


def _run_driver(tmp_path: Path, ledger: Path, verb: str, now: float) -> dict:
    driver = tmp_path / "driver.py"
    if not driver.exists():
        driver.write_text(_DRIVER, encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable,
            str(driver),
            str(REPO / "scripts"),
            str(REPO),
            str(ledger),
            verb,
            repr(now),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"driver {verb} failed: {proc.stderr[-2000:]}"
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_the_VERDICT_survives_a_REAL_PROCESS_BOUNDARY_not_merely_a_new_object(
    tmp_path: Path, knobs: SupervisionKnobs
) -> None:
    """§0a/1: a module-level cache would satisfy a same-interpreter second
    object. The event §4:274 must survive is a new PROCESS, so one is forked."""
    ledger = tmp_path / "restarts.jsonl"
    empty = _run_driver(tmp_path, ledger, "probe", 1000.0)
    written = _run_driver(tmp_path, ledger, "crash", 1000.0)
    read_back = _run_driver(tmp_path, ledger, "probe", 1000.0)

    assert empty["is_quarantined"] is False, "non-vacuity: the empty book said YES"
    assert len({empty["pid"], written["pid"], read_back["pid"]}) == 3
    assert read_back["is_quarantined"] is True, read_back["reason"]
    assert read_back["may_relaunch"] is False
    assert f"restarts_in_window={knobs.crash_loop_max}" in read_back["reason"]

    restored = _run_driver(tmp_path, ledger, "restore", 1000.5)
    after = _run_driver(tmp_path, ledger, "probe", 1000.5)
    assert restored["restarts_in_window"] == knobs.crash_loop_max - 1
    assert after["restarts_in_window"] == knobs.crash_loop_max - 1, after["reason"]
    assert after["is_quarantined"] is False
