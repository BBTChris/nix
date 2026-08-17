"""ARC 034 / sub-agent C — §12.2's crash-loop breaker, driven until it TRIPS.

The can-fail suite for `scripts/nixrisk/supervision.py` and
`scripts/nix_crash_loop_halt.py`. Every control follows plant → red (naming the
SITE and the REASON) → restore → green, and every assertion reads the REASON — a
`HaltCause`, an alert code, a counted-stamp list, a JSON field — never an exit
code or a bare boolean (check contract v2 §11).

Every `§` cites `docs/nics_risk_subsystem_spec_v1.3.md` unless another document
is named on the same line.

THE §0a HAZARDS THIS BRIEF NAMES, TREATED AS HYPOTHESES AND MEASURED:

* **a breaker that never crash-loops never exercises the cap.** So the cap is
  driven at `max` restarts (the trip), at `max + 1` (still tripped), and at
  `max - 1` (must NOT trip). A suite that only counted to two would leave the
  entire tripping branch dead.
* **a breaker that trips on any N restarts EVER has no window, and the window is
  the whole tunable.** So `max` restarts spread ACROSS the window boundary must
  NOT trip, and the boundary INSTANT is driven from both sides — one epsilon
  inside counts, exactly `window_s` old does not.
* **a counter in the crashing process's memory counts to one forever.** So the
  ledger is driven through TWO objects over ONE path, which is what a restart
  looks like, and through two real SUBPROCESSES of the systemd actuator.
* **a non-vacuity floor that is an arithmetic identity measures nothing.** So the
  falsifiers here are subjects, not constants: `_NoWindowBreaker` counts every
  restart ever and is shown to trip where the real one does not.
"""

# pylint: disable=invalid-name,redefined-outer-name,protected-access
# pylint: disable=missing-function-docstring,too-few-public-methods
# invalid-name: the test names are sentences. redefined-outer-name: pytest
# fixtures. protected-access: the falsifier reaches the breaker's own knobs to
# build a WRONG variant — that is how a falsifier is written.
# missing-function-docstring: each double's verbs are named after the port they
# stand in for. too-few-public-methods: the sinks are one-verb stand-ins.
# pylint: disable=missing-class-docstring,use-implicit-booleaness-not-comparison
# pylint: disable=import-outside-toplevel
# C1803: `x == []` is the assertion — 'exactly nothing was raised' is a
# different claim from 'nothing truthy was raised', and the failure message
# shows WHAT was there instead.

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

# pylint: disable=wrong-import-position
import risk_config
from nixrisk.halt import HaltCause
from nixrisk.supervision import (
    KNOB_KEYS,
    SCORE_BOUNDARY,
    BreakerScope,
    CrashLoopBreaker,
    RestartLedger,
    SupervisionKnobError,
    SupervisionKnobs,
    SupervisionUsageError,
    read_unit_policy,
    unit_policy_defects,
)

DROP_IN = REPO / "scripts" / "nix-supervision.conf"
ACTUATOR = REPO / "scripts" / "nix_crash_loop_halt.py"


# ==========================================================================
# Doubles — each one verb, each recording the REASON and not a count
# ==========================================================================


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
        return f"{event} {fields}"

    def events(self) -> list[str]:
        return [event for event, _ in self.lines]


class Halts:
    """The §12.5 setter half. Records the CAUSE and the REASON, not a call count."""

    def __init__(self) -> None:
        self.sets: list[tuple[HaltCause, str, float | None]] = []

    def set(self, cause, reason: str, *, now: float | None = None):
        self.sets.append((cause, reason, now))
        return cause


class _NoWindowBreaker(CrashLoopBreaker):
    """THE FALSIFIER: a breaker with NO window — it counts every restart ever.

    This is what the window's ABSENCE looks like, and it is the object that makes
    the boundary controls non-vacuous: they assert the real breaker does NOT trip
    in a case where this one does.
    """

    def restarts_in_window(self, subject: str, now: float):
        del now
        return tuple(rec for rec in self._ledger.records() if rec.subject == subject)


# ==========================================================================
# Fixtures
# ==========================================================================


@pytest.fixture
def knobs() -> SupervisionKnobs:
    """The SHIPPED tunables, read from risks/ — never typed into this file.

    §0a: a suite that hard-coded 3 and 10 would agree with itself while the
    config said something else. The gate does the same thing for the same reason.
    """
    loaded = risk_config.load_risk_configs(REPO)
    return SupervisionKnobs.from_config(loaded.modules["supervision"].values)


def _breaker(tmp_path: Path, knobs: SupervisionKnobs, scope: BreakerScope, **kw):
    alerts = Alerts()
    plane2 = Plane2()
    halts = Halts() if scope is BreakerScope.PROCESS else None
    cls = kw.pop("cls", CrashLoopBreaker)
    breaker = cls(
        knobs=knobs,
        scope=scope,
        ledger=RestartLedger(tmp_path / "restarts.jsonl"),
        alert=alerts,
        plane2=plane2,
        halt=halts,
        **kw,
    )
    return breaker, alerts, plane2, halts


# ==========================================================================
# C1 — THE BREAKER ACTUALLY TRIPS, and the window is real
# ==========================================================================


def test_the_cap_TRIPS_at_exactly_MAX_restarts_inside_the_window_and_HALTS(
    tmp_path: Path, knobs: SupervisionKnobs
) -> None:
    """§12.2:617 — 'N restarts in M minutes ⇒ HALT + operator alert'. Driven to N.

    §7.12/1: the tripping branch is not dead code here — it is reached, and the
    assertion reads the §12.5 CAUSE and the alert CODE, never a return value.
    """
    breaker, alerts, plane2, halts = _breaker(tmp_path, knobs, BreakerScope.PROCESS)
    step = knobs.window_s / (knobs.crash_loop_max + 2)

    verdicts = [
        breaker.record_restart("nix-limiter.service", now=1000.0 + step * i)
        for i in range(knobs.crash_loop_max)
    ]

    under = verdicts[:-1]
    assert not any(v.tripped for v in under), [v.reason for v in under]
    final = verdicts[-1]
    assert final.tripped, final.reason
    assert final.restarts_in_window == knobs.crash_loop_max, final.reason
    assert "CRASH-LOOP CAP HIT" in final.reason
    assert final.halted is True and final.quarantined is False, final.reason
    assert halts is not None
    assert [cause for cause, _, _ in halts.sets] == [HaltCause.CRASH_LOOP], halts.sets
    assert "CRASH-LOOP CAP HIT" in halts.sets[0][1]
    assert alerts.codes() == ["supervision.crash-loop-halt"], alerts.raised
    assert "Never blind restart-into-trading" in alerts.raised[0][1]
    assert plane2.events() == ["crash-loop-count"] * knobs.crash_loop_max
    assert plane2.lines[-1][1]["cap_hit"] is True


def test_MAX_PLUS_ONE_restarts_inside_the_window_STILL_trips(
    tmp_path: Path, knobs: SupervisionKnobs
) -> None:
    """The brief's N+1 drive. A cap that only fired on the exact Nth restart and
    then forgot would leave a crash loop running from the (N+1)th onward."""
    breaker, alerts, _, halts = _breaker(tmp_path, knobs, BreakerScope.PROCESS)
    step = knobs.window_s / (knobs.crash_loop_max + 3)

    verdicts = [
        breaker.record_restart("nix-limiter.service", now=2000.0 + step * i)
        for i in range(knobs.crash_loop_max + 1)
    ]

    assert verdicts[-1].tripped, verdicts[-1].reason
    assert verdicts[-1].restarts_in_window == knobs.crash_loop_max + 1
    assert halts is not None and len(halts.sets) == 2, halts.sets
    assert alerts.codes() == ["supervision.crash-loop-halt"] * 2


def test_MAX_restarts_spread_ACROSS_the_window_boundary_does_NOT_trip(
    tmp_path: Path, knobs: SupervisionKnobs
) -> None:
    """THE WINDOW IS THE WHOLE TUNABLE. §12.2:617's M minutes, driven.

    The restarts are spaced so that at every verdict fewer than `max` of them lie
    inside the window. A breaker that trips on N restarts EVER has no window at
    all, and `_NoWindowBreaker` below proves this control can fail.
    """
    breaker, alerts, _, halts = _breaker(tmp_path, knobs, BreakerScope.PROCESS)
    # One restart every 0.8 windows: any two adjacent ones straddle the boundary.
    step = knobs.window_s * 0.8

    verdicts = [
        breaker.record_restart("nix-limiter.service", now=3000.0 + step * i)
        for i in range(knobs.crash_loop_max)
    ]

    assert not any(v.tripped for v in verdicts), [v.reason for v in verdicts]
    assert all(v.restarts_in_window < knobs.crash_loop_max for v in verdicts)
    assert "under the cap" in verdicts[-1].reason
    assert halts is not None and halts.sets == [], halts.sets
    assert alerts.raised == [], alerts.raised


def test_the_ACROSS_BOUNDARY_control_is_FALSIFIABLE_a_windowless_breaker_TRIPS(
    tmp_path: Path, knobs: SupervisionKnobs
) -> None:
    """The can-fail twin of the control above: `_NoWindowBreaker` counts every
    restart ever, so the SAME spacing trips it. Without this the previous test
    would pass over a breaker with no window and measure nothing."""
    breaker, _, _, halts = _breaker(
        tmp_path, knobs, BreakerScope.PROCESS, cls=_NoWindowBreaker
    )
    step = knobs.window_s * 0.8

    verdicts = [
        breaker.record_restart("nix-limiter.service", now=3000.0 + step * i)
        for i in range(knobs.crash_loop_max)
    ]

    assert verdicts[-1].tripped, (
        "the windowless falsifier did not trip — it no longer falsifies"
    )
    assert halts is not None and halts.sets, "the falsifier declared no HALT"


def test_the_WINDOW_BOUNDARY_INSTANT_is_driven_from_BOTH_sides(
    tmp_path: Path, knobs: SupervisionKnobs
) -> None:
    """§0a: 'boundary instants never driven, on gates whose entire safety property
    is a boundary'. The window is half-open — `now - ts < window_s` counts and
    `now - ts == window_s` has EXPIRED — so both instants are driven here.

    Two restarts land at `t0`; the third lands EXACTLY one window after the first
    (so the first has expired: 2 in window, no trip) and then one epsilon earlier
    (so the first still counts: 3 in window, trip). The two cases differ by one
    epsilon of clock and by nothing else.
    """
    epsilon = 1e-6
    t0 = 5000.0
    inner = [t0, t0 + epsilon]

    exact, _, _, halts_exact = _breaker(tmp_path / "a", knobs, BreakerScope.PROCESS)
    for stamp in inner:
        exact.record_restart("u", now=stamp)
    at_boundary = exact.record_restart("u", now=t0 + knobs.window_s)

    assert at_boundary.restarts_in_window == knobs.crash_loop_max - 1, (
        at_boundary.reason
    )
    assert not at_boundary.tripped, at_boundary.reason
    assert halts_exact is not None and halts_exact.sets == []

    inside, _, _, halts_inside = _breaker(tmp_path / "b", knobs, BreakerScope.PROCESS)
    for stamp in inner:
        inside.record_restart("u", now=stamp)
    just_inside = inside.record_restart("u", now=t0 + knobs.window_s - epsilon)

    assert just_inside.restarts_in_window == knobs.crash_loop_max, just_inside.reason
    assert just_inside.tripped, just_inside.reason
    assert halts_inside is not None
    assert [c for c, _, _ in halts_inside.sets] == [HaltCause.CRASH_LOOP]


def test_two_subjects_are_counted_SEPARATELY(
    tmp_path: Path, knobs: SupervisionKnobs
) -> None:
    """One unit's crash loop must not cap a different unit. A shared counter would
    HALT the platform because two unrelated processes each restarted twice."""
    breaker, _, _, halts = _breaker(tmp_path, knobs, BreakerScope.PROCESS)

    for i in range(knobs.crash_loop_max):
        breaker.record_restart("unit-a", now=6000.0 + i)
        last_b = breaker.record_restart("unit-b", now=6000.5 + i)

    assert last_b.restarts_in_window == knobs.crash_loop_max, last_b.reason
    assert halts is not None and len(halts.sets) == 2, [s[1] for s in halts.sets]
    assert all("unit-a" in r or "unit-b" in r for _, r, _ in halts.sets)


# ==========================================================================
# The counter must SURVIVE the crash — that is why it is on disk
# ==========================================================================


def test_the_RESTART_LEDGER_survives_a_new_process_because_it_is_ON_DISK(
    tmp_path: Path, knobs: SupervisionKnobs
) -> None:
    """§7.12/4: a counter in the crashing process's memory counts to one forever.

    Two `CrashLoopBreaker` objects over ONE ledger path IS what a restart looks
    like: the second sees the first's restarts and trips on the last one.
    """
    path = tmp_path / "restarts.jsonl"
    alerts, plane2 = Alerts(), Plane2()

    def fresh_process():
        return CrashLoopBreaker(
            knobs=knobs,
            scope=BreakerScope.STRATEGY,
            ledger=RestartLedger(path),
            alert=alerts,
            plane2=plane2,
        )

    for i in range(knobs.crash_loop_max - 1):
        fresh_process().record_restart("strat-1", now=7000.0 + i)
    final = fresh_process().record_restart("strat-1", now=7000.0 + knobs.crash_loop_max)

    assert final.restarts_in_window == knobs.crash_loop_max, final.reason
    assert final.tripped and final.quarantined, final.reason
    assert alerts.codes() == ["supervision.quarantine"], alerts.raised


def test_a_DAMAGED_ledger_line_is_REPORTED_and_never_silently_skipped(
    tmp_path: Path,
) -> None:
    """Directive 4. Skipping an unparsable record would move a subject back BELOW
    the cap by losing the count, which is the cap failing OPEN."""
    path = tmp_path / "restarts.jsonl"
    ledger = RestartLedger(path)
    ledger.record("u", 1.0)
    with path.open("a", encoding="utf-8") as handle:
        handle.write("{not json}\n")

    with pytest.raises(SupervisionUsageError) as caught:
        ledger.records()

    assert "is not a restart record" in str(caught.value)
    assert "a crash loop the cap will not see" in str(caught.value)


# ==========================================================================
# C3 — the STRATEGY cap quarantines and does NOT halt the platform
# ==========================================================================


def test_the_STRATEGY_cap_QUARANTINES_and_declares_NO_HALT(
    tmp_path: Path, knobs: SupervisionKnobs
) -> None:
    """§4:272-274 — 'quarantined — left dead and flat, alert raised — while the
    rest of the system keeps trading'. The absence of a HALT is the property, and
    it is enforced at CONSTRUCTION: a STRATEGY breaker cannot hold a HALT flag."""
    breaker, alerts, plane2, halts = _breaker(tmp_path, knobs, BreakerScope.STRATEGY)
    assert halts is None

    for i in range(knobs.crash_loop_max):
        verdict = breaker.record_restart("strat-1", now=8000.0 + i)

    assert verdict.tripped and verdict.quarantined, verdict.reason
    assert verdict.halted is False, verdict.reason
    assert breaker.is_quarantined("strat-1")
    allowed, why = breaker.may_relaunch("strat-1")
    assert allowed is False
    assert "QUARANTINED" in why and "quarantine-restore" in why
    assert alerts.codes() == ["supervision.quarantine"], alerts.raised
    assert "the rest of the system keeps trading" in alerts.raised[0][1]
    assert SCORE_BOUNDARY in alerts.raised[0][1], (
        "the quarantine alert must carry the R5 scoring boundary — a green here "
        "must not imply score archival happened"
    )
    assert plane2.lines[-1][1]["quarantined"] is True


def test_a_quarantined_strategy_returns_ONLY_by_the_OPERATOR_verb(
    tmp_path: Path, knobs: SupervisionKnobs
) -> None:
    """§4:274 — 'NOT auto-resurrected; return is operator-driven'. §12.11:779's
    `quarantine-restore` also RESETS the crash-loop counter, and the reset is a
    new FLOOR rather than a deletion (directive 6: the ledger is append-only)."""
    breaker, alerts, plane2, _ = _breaker(tmp_path, knobs, BreakerScope.STRATEGY)
    for i in range(knobs.crash_loop_max):
        breaker.record_restart("strat-1", now=9000.0 + i)
    before = len(RestartLedger(tmp_path / "restarts.jsonl").records())

    lifted = breaker.restore("strat-1", operator="bbt", now=9050.0)

    assert lifted is not None and lifted.quarantined
    assert not breaker.is_quarantined("strat-1")
    allowed, why = breaker.may_relaunch("strat-1")
    assert allowed is True and "not quarantined" in why
    assert "quarantine-restore" in plane2.events()
    assert alerts.codes()[-1] == "supervision.quarantine-restore"
    assert SCORE_BOUNDARY in alerts.raised[-1][1]
    after = RestartLedger(tmp_path / "restarts.jsonl").records()
    assert len(after) == before, (
        "restore DELETED ledger records — §12.11:779 resets the counter; "
        "directive 6 forbids rewriting banked evidence to do it"
    )
    next_verdict = breaker.record_restart("strat-1", now=9100.0)
    assert next_verdict.restarts_in_window == 1, next_verdict.reason


def test_a_PROCESS_breaker_with_NO_HALT_FLAG_is_REFUSED_at_construction(
    tmp_path: Path, knobs: SupervisionKnobs
) -> None:
    """The can-fail: §12.2:617's consequence is HALT. A breaker that can only log
    counts correctly and never stops the money."""
    with pytest.raises(SupervisionUsageError) as caught:
        CrashLoopBreaker(
            knobs=knobs,
            scope=BreakerScope.PROCESS,
            ledger=RestartLedger(tmp_path / "l.jsonl"),
            alert=Alerts(),
            plane2=Plane2(),
        )

    assert "a PROCESS-scope breaker needs the §12.5 HALT flag" in str(caught.value)
    assert "blind restart-into-trading" in str(caught.value)


def test_a_STRATEGY_breaker_HOLDING_a_halt_flag_is_REFUSED_at_construction(
    tmp_path: Path, knobs: SupervisionKnobs
) -> None:
    """The other side, and the one that would cost money: one strategy's crash
    loop must not stop the platform (§4:273)."""
    with pytest.raises(SupervisionUsageError) as caught:
        CrashLoopBreaker(
            knobs=knobs,
            scope=BreakerScope.STRATEGY,
            ledger=RestartLedger(tmp_path / "l.jsonl"),
            alert=Alerts(),
            plane2=Plane2(),
            halt=Halts(),
        )

    assert "must NOT hold a HALT flag" in str(caught.value)
    assert "that rule inverted" in str(caught.value)


# ==========================================================================
# The knobs — §12A boot validation, refused rather than defaulted
# ==========================================================================


@pytest.mark.parametrize(
    ("bad", "phrase"),
    [
        ({"crash_loop_max": 0, "crash_loop_window_min": 10}, "on its FIRST crash"),
        ({"crash_loop_max": 3, "crash_loop_window_min": 0}, "never trips"),
        ({"crash_loop_max": -1, "crash_loop_window_min": 10}, "must be > 0"),
    ],
)
def test_an_INVALID_KNOB_SET_is_REFUSED_naming_what_it_would_break(
    bad: dict, phrase: str
) -> None:
    """§12A:801-802 rejects an invalid set 'before any strategy registers'. The
    refusal names the FAILURE, not the range: 'must be > 0' alone does not say
    that a zero cap quarantines on the first crash."""
    with pytest.raises(SupervisionKnobError) as caught:
        SupervisionKnobs.from_config(bad)

    assert phrase in str(caught.value)


def test_an_ABSENT_knob_is_a_REFUSAL_and_never_a_default() -> None:
    """Directive 4 and `risk_config`'s own rule: no defaulted read on the boot
    path, because an absent knob must be a refusal and not a number nobody chose."""
    with pytest.raises(SupervisionKnobError) as caught:
        SupervisionKnobs.from_config({"crash_loop_max": 3})

    assert "crash_loop_window_min" in str(caught.value)
    assert "holds no default" in str(caught.value)


def test_the_SHIPPED_config_carries_exactly_the_knobs_this_module_declares() -> None:
    """Both sides derived: `KNOB_KEYS` against the file, not against a literal."""
    loaded = risk_config.load_risk_configs(REPO)
    values = loaded.modules["supervision"].values

    assert set(KNOB_KEYS) <= set(values), sorted(values)
    knobs = SupervisionKnobs.from_config(values)
    assert knobs.window_s == knobs.crash_loop_window_min * 60.0


# ==========================================================================
# The systemd side — unit FILES, read as files. Nothing installed.
# ==========================================================================


def test_the_SHIPPED_DROP_IN_carries_the_policy_the_KNOBS_declare(
    knobs: SupervisionKnobs,
) -> None:
    """§12.2:616 + the derivation rule: systemd's own limiter and this breaker
    must count to the SAME numbers, or whichever fires first decides and the
    tunable is a fiction. Both sides are derived — the expected figures come from
    risks/supervision.config.json, never from a literal in this file."""
    policy = read_unit_policy(DROP_IN)

    assert unit_policy_defects(policy, knobs) == []
    assert policy.restarts, policy.restart
    assert policy.start_limit_burst == knobs.crash_loop_max
    assert policy.start_limit_interval_s == knobs.window_s
    assert policy.start_limit_action == "none"
    assert policy.on_failure == ("nix-crash-loop-halt@%n.service",)


@pytest.mark.parametrize(
    ("line", "replacement", "phrase"),
    [
        ("Restart=always", "Restart=no", "requires every process"),
        ("StartLimitBurst=3", "StartLimitBurst=9", "count to different numbers"),
        ("StartLimitIntervalSec=600", "StartLimitIntervalSec=60", "same window"),
        ("StartLimitAction=none", "StartLimitAction=reboot", "expected 'none'"),
        ("OnFailure=nix-crash-loop-halt@%n.service", "X=1", "counter with no input"),
    ],
)
def test_a_PLANTED_unit_policy_defect_is_NAMED(
    tmp_path: Path, knobs: SupervisionKnobs, line: str, replacement: str, phrase: str
) -> None:
    """Five can-fail controls, one per §12.2 requirement. Each asserts the REASON
    the reader is given, never that 'a defect was found'."""
    text = DROP_IN.read_text(encoding="utf-8")
    assert line in text, f"the fixture no longer contains {line!r}"
    planted = tmp_path / "planted.conf"
    planted.write_text(text.replace(line, replacement), encoding="utf-8")

    defects = unit_policy_defects(read_unit_policy(planted), knobs)

    assert defects, f"planting {line!r} -> {replacement!r} produced no defect"
    assert any(phrase in d for d in defects), defects


def test_this_arc_INSTALLED_NOTHING_and_that_is_MEASURED_not_promised() -> None:
    """The hard rule: no enable, no start, no `daemon-reload` on a box running a
    live IB Gateway. A read of a directory, and nothing else."""
    from nixrisk.supervision import (
        not_installed,  # pylint: disable=import-outside-toplevel
    )

    sentence = not_installed(["nix-crash-loop-halt@.service", "nix-supervision.conf"])

    assert "installed, enabled, started and reloaded nothing" in sentence, sentence


# ==========================================================================
# The systemd ACTUATOR, driven as systemd drives it: separate processes
# ==========================================================================


def _actuate(tmp_path: Path, unit: str, now: float) -> dict:
    proc = subprocess.run(
        [
            sys.executable,
            str(ACTUATOR),
            "--unit",
            unit,
            "--home",
            str(REPO),
            "--ledger",
            str(tmp_path / "restarts.jsonl"),
            "--marker",
            str(tmp_path / "halt.marker"),
            "--now",
            repr(now),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.stdout.strip(), proc.stderr
    return json.loads(proc.stdout.strip())


def test_the_ACTUATOR_counts_ACROSS_PROCESSES_and_writes_a_HALT_MARKER_at_the_cap(
    tmp_path: Path, knobs: SupervisionKnobs
) -> None:
    """§12.5:634-638 by name: the Limiter may BE the crash-looping process, so the
    HALT is recorded as a marker and booked into Plane 1 at next boot. Each
    invocation is a REAL subprocess, which is how systemd will run it.

    Asserts the JSON REASON and the marker's own recorded CAUSE — never the exit
    code, which is a shared namespace (check contract v2 §11).
    """
    marker = tmp_path / "halt.marker"
    reports = [
        _actuate(tmp_path, "nix-ibgateway.service", 10_000.0 + i)
        for i in range(knobs.crash_loop_max)
    ]

    assert [r["restarts_in_window"] for r in reports] == list(
        range(1, knobs.crash_loop_max + 1)
    ), reports
    assert [r["cap_hit"] for r in reports] == [False] * (knobs.crash_loop_max - 1) + [
        True
    ]
    assert not marker.exists() or reports[-1]["cap_hit"]
    assert reports[-1]["halt_cause"] == HaltCause.CRASH_LOOP.value
    assert reports[-1]["cap"] == knobs.crash_loop_max
    assert reports[-1]["window_s"] == knobs.window_s
    assert SCORE_BOUNDARY == reports[-1]["score_boundary"]

    lines = [json.loads(raw) for raw in marker.read_text().splitlines() if raw.strip()]
    assert [entry["rec"] for entry in lines] == ["set"], lines
    assert lines[0]["cause"] == HaltCause.CRASH_LOOP.value
    assert "CAP" in lines[0]["reason"].upper() or "cap" in lines[0]["reason"]
    assert "nix-ibgateway.service" in lines[0]["reason"]


def test_the_ACTUATOR_writes_NO_MARKER_below_the_cap(
    tmp_path: Path, knobs: SupervisionKnobs
) -> None:
    """The can-fail twin: an actuator that wrote a marker on every failure would
    HALT the platform on the first crash, which §12.2:618 says is safe by design."""
    for i in range(knobs.crash_loop_max - 1):
        report = _actuate(tmp_path, "nix-xvfb.service", 20_000.0 + i)
        assert report["cap_hit"] is False, report["reason"]
        assert report["marker"] == "", report

    assert not (tmp_path / "halt.marker").exists()


def test_the_ACTUATOR_REFUSES_to_run_on_a_config_it_cannot_load(
    tmp_path: Path,
) -> None:
    """Directive 4, fail closed and loud: no defaulted cap. The refusal names the
    file, not just a status."""
    empty_home = tmp_path / "no-risks"
    empty_home.mkdir()
    proc = subprocess.run(
        [sys.executable, str(ACTUATOR), "--unit", "u", "--home", str(empty_home)],
        capture_output=True,
        text=True,
        check=False,
    )

    report = json.loads(proc.stdout.strip())
    assert report["ok"] is False
    assert "risks/supervision.config.json" in report["reason"]
    assert "defaulted knobs" in report["reason"]
