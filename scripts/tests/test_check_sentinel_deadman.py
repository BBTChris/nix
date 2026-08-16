"""ARC 034 / B — the can-fail suite for the §12.1 deadman gate.

Structure follows `docs/nix_check_contract.md` §5.1: non-vacuity FIRST, then one
control per DECLARED ARM that must FAIL and NAME its site, then the same
population passing unperturbed. A demonstration missing the last step shows only
that a gate can fail.

**EVERY CONTROL ASSERTS THE REASON** — a substring of `site` or `detail` naming
WHAT was wrong — never a status and never an exit code (check contract v2 §11 /
§18). `FAIL_NEEDS_OPERATOR` is one integer shared by eleven arms.

**No control touches a production artifact** (doctrine C.8, `docs/CHECK-DEBT.md`
D3.189). The arms are pure functions over a drill's observations, so most
controls hand them a PERTURBED OBSERVATION rather than perturbing the tree; the
three that must read files build a throwaway `nix_home` under `tmp_path`.

**Why the arms are driven separately from the end-to-end run.** The gate spawns
two real interpreters per drill arm and kills one of them; running the whole gate
once per control would cost half a minute and would tell a failing control's
reader nothing about WHICH arm broke. So there is exactly ONE end-to-end control
— `test_the_GATE_PASSES_ON_THE_REAL_TREE_and_its_evidence_names_the_SIGKILL` —
and it is the one that proves the arms below are wired to anything at all.
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# pylint: disable=protected-access,too-few-public-methods
# pylint: disable=too-many-instance-attributes
# pylint: disable=use-implicit-booleaness-not-comparison
# protected-access: `gate._authorised_verbs` and `gate._floor_refusal` are the
# two arms whose whole subject is that they are NOT part of the gate's public
# surface — one derives the expected side from the frozen seam, the other decides
# CANNOT_MEASURE. Driving them through `run()` would cost two process launches
# per control and would report a composite verdict instead of the arm's own.
# C1803 (`x == []`): REFUSED. `not x` passes for None and for any falsey object,
# and "the arm found nothing" must mean the EMPTY LIST rather than anything
# falsey — an arm that returned None would satisfy the simplification silently.
# Test names SHOUT the property; the sys.path bootstrap is identical in every
# check test by requirement.

from __future__ import annotations

import json
import shutil
import signal
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
# APPENDED, never inserted at the front — loader.py's failure mode #8 note.
sys.path.append(str(REPO / "checks"))

import check_sentinel_deadman as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)


@dataclass
class FakeDrill:
    """A drill OBSERVATION, shaped exactly as `run_drill` returns one.

    Not a stand-in for the drill: the end-to-end control below runs the real one.
    This is how a control hands ONE arm a single perturbed fact without paying
    for two process launches to produce it.
    """

    publisher_pid: int = 111
    publisher_status: int | None = -signal.SIGKILL
    sentinel_pid: int | None = 222
    sentinel_returncode: int | None = 0
    wakes: tuple = ()
    marker_records: tuple = ()
    broker_calls: tuple = ()
    alerts: tuple = ()
    detail: str = ""


def _wake(**kw) -> dict:
    """One wake, JSON-shaped as the drill child writes it."""
    base = {
        "cause": "heartbeat_lost",
        "acted": True,
        "liveness": "progressing",
        "symbols": ["MES"],
        "observed_pid": 111,
        "stale": True,
        "no_progress": True,
        "detail": "",
    }
    base.update(kw)
    return base


def _rec(phase: str, **kw) -> dict:
    """One marker record, JSON-shaped as `MarkerReplay` dumps it."""
    base = {
        "phase": phase,
        "cause": "heartbeat_lost",
        "ts": 1000.0 if phase == "before" else 1001.0,
        "symbols": ["MES"],
        "acks": []
        if phase == "before"
        else [{"symbol": "MES", "ok": True, "detail": ""}],
        "sentinel_pid": 222,
        "heartbeat_age_s": 9.0,
    }
    base.update(kw)
    return base


def _good_kill() -> FakeDrill:
    """A drill in which everything §12.1:604-606 requires actually happened."""
    return FakeDrill(
        wakes=(_wake(acted=False, cause=None), _wake()),
        marker_records=(_rec("before"), _rec("after")),
        broker_calls=tuple({"verb": verb} for verb in gate._EXPECTED_SESSION),
    )


def _sites(defects) -> str:
    """Every site and reason, joined — what a control asserts against."""
    return "; ".join(f"{site}: {why}" for site, why in defects)


# ==========================================================================
# NON-VACUITY FIRST — the gate is real, registered, and covers its artifacts
# ==========================================================================


def test_the_GATE_PASSES_ON_THE_REAL_TREE_and_its_evidence_names_the_SIGKILL() -> None:
    """The end-to-end control. Two real interpreters per arm, one really killed.

    The evidence is asserted, not the status: a PASS whose evidence does not name
    the kernel's reaped status has not shown that anything was killed, and
    `nixverify.contract.validate_result` would have accepted an empty-ish string.
    """
    result = gate.run(Mode.VERIFY, Context(nix_home=REPO, mode=Mode.VERIFY))

    assert result.status is Status.PASS, result.detail
    assert f"reaped {-signal.SIGKILL}" in result.evidence, result.evidence
    assert "marker ['before', 'after']" in result.evidence, result.evidence
    assert "rc 97" in result.evidence, result.evidence
    assert "nixrisk in the Sentinel's import closure: []" in result.evidence


def test_the_GATE_DECLARES_EVERY_ARTIFACT_IT_INTRODUCES_as_a_SUBJECT() -> None:
    """`check_artifact_gate_coverage` FAILs on a tracked artifact no gate names,
    and the coverage ratchet may only shrink. Asserted here so the obligation is
    visible next to the gate rather than only in the ratchet's output."""
    owed = {
        "scripts/nixsentinel/watchdog.py",
        "scripts/nixsentinel/marker.py",
        "scripts/nixsentinel/heartbeat.py",
        "scripts/nixsentinel/config.py",
        "scripts/sentinel_kill_drill.py",
        "risks/sentinel.config.json",
    }

    missing = owed - set(gate.SUBJECTS)

    assert not missing, missing
    for rel in gate.SUBJECTS:
        assert (REPO / rel).is_file(), rel


def test_the_GATE_IS_IN_THE_EXECUTION_PLAN_or_it_never_runs() -> None:
    """A gate the runner does not know about is a gate that has never judged
    anything, and `verify.py --optimize` reports an orphan loudly."""
    payload = json.loads(
        (REPO / "checks" / "registry.json").read_text(encoding="utf-8")
    )
    names = {name for block in payload["blocks"] for name in block["checks"]}

    assert gate.NAME in names, sorted(names)


# ==========================================================================
# ARM 1 — the kill
# ==========================================================================


def test_ARM1_REDDENS_when_the_publisher_EXITED_rather_than_being_KILLED() -> None:
    """A publisher that returned 0 tidied up first. §12.1:604 is about a Risk
    Engine that was killed, and a drill that let it exit measured a shutdown."""
    defects = gate.kill_defects(FakeDrill(publisher_status=0, **_extra()), 5)

    assert "not -9 (-SIGKILL)" in _sites(defects) or "-SIGKILL" in _sites(defects)
    assert "is not a killed Limiter" in _sites(defects), _sites(defects)


def _extra() -> dict:
    """The fields a kill control keeps healthy while perturbing one."""
    good = _good_kill()
    return {
        "wakes": good.wakes,
        "marker_records": good.marker_records,
        "broker_calls": good.broker_calls,
    }


def test_ARM1_REDDENS_when_the_SENTINEL_NEVER_WATCHED_A_LIVE_RISK_ENGINE() -> None:
    """If the heartbeat was never seen advancing, 'lost' was never a change and
    the drill measured a Sentinel that has watched nothing alive."""
    defects = gate.kill_defects(_good_kill(), gate.MIN_LIVE_WAKES - 1)

    assert "PROGRESSING Risk Engine" in _sites(defects), _sites(defects)
    assert "was never a change" in _sites(defects), _sites(defects)


def test_ARM1_REDDENS_when_a_REAL_KILL_WITH_OPEN_POSITIONS_produced_NO_FLATTEN() -> (
    None
):
    """The headline property, inverted. Both halves of §12.1:604-605 were true."""
    outcome = _good_kill()
    outcome.wakes = (_wake(acted=False, cause=None),)

    defects = gate.kill_defects(outcome, 5)

    assert "never flattened after a real SIGKILL" in _sites(defects), _sites(defects)


def test_ARM1_REDDENS_when_the_FLATTEN_CANNOT_BE_ATTRIBUTED_TO_THE_DEATH() -> None:
    """A flatten whose observed pid is not the pid that was killed is a flatten
    with no proven cause — the ARC 033 attribution class, one component over."""
    outcome = _good_kill()
    outcome.wakes = (_wake(observed_pid=999),)

    defects = gate.kill_defects(outcome, 5)

    assert "attributed the loss to pid 999" in _sites(defects), _sites(defects)
    assert "killed pid 111" in _sites(defects), _sites(defects)


def test_ARM1_REDDENS_when_the_MARKER_HAS_NO_BEFORE_RECORD() -> None:
    """§12.1:610 requires a record on BOTH sides of the act."""
    outcome = _good_kill()
    outcome.marker_records = (_rec("after"),)

    defects = gate.kill_defects(outcome, 5)

    assert "not ('before', 'after')" in _sites(defects), _sites(defects)


def test_ARM1_REDDENS_when_the_BEFORE_RECORD_CARRIES_ACKNOWLEDGEMENTS() -> None:
    """The `before` record is written before one instruction reaches the broker,
    so there is nothing that could have acknowledged anything. An ack there means
    the record was written AFTER the send and the ordering is a fiction."""
    outcome = _good_kill()
    outcome.marker_records = (
        _rec("before", acks=[{"symbol": "MES", "ok": True, "detail": "x"}]),
        _rec("after"),
    )

    defects = gate.kill_defects(outcome, 5)

    assert "nothing that could have acknowledged" in _sites(defects), _sites(defects)


def test_ARM1_REDDENS_when_the_MARKER_RECORDS_DIFFERENT_SYMBOLS_than_were_closed() -> (
    None
):
    """A record that names the wrong instruments cannot be replayed into Plane 1."""
    outcome = _good_kill()
    outcome.marker_records = (_rec("before"), _rec("after", symbols=["ES"]))

    defects = gate.kill_defects(outcome, 5)

    assert "records symbols ['ES']" in _sites(defects), _sites(defects)


# ==========================================================================
# ARM 2 — the control
# ==========================================================================


def test_ARM2_REDDENS_when_the_SENTINEL_FLATTENED_A_LIVE_RISK_ENGINE() -> None:
    """§14:977 keeps flatten execution Limiter-only while the Limiter lives."""
    defects = gate.control_defects(FakeDrill(wakes=tuple(_wake() for _ in range(20))))

    assert "against a LIVE Risk Engine" in _sites(defects), _sites(defects)


def test_ARM2_REDDENS_when_THE_CONTROL_SENTINEL_BARELY_RAN() -> None:
    """'It did nothing' is a statement about a Sentinel that never ran."""
    defects = gate.control_defects(
        FakeDrill(wakes=tuple(_wake(acted=False, cause=None) for _ in range(2)))
    )

    assert "below the floor" in _sites(defects), _sites(defects)
    assert "proved nothing" in _sites(defects), _sites(defects)


def test_ARM2_REDDENS_when_THE_SESSION_IS_KEPT_WARM_against_a_living_Limiter() -> None:
    """§12.1:605's own session is opened when the condition fires."""
    defects = gate.control_defects(
        FakeDrill(
            wakes=tuple(_wake(acted=False, cause=None) for _ in range(20)),
            broker_calls=({"verb": "connect"},),
        )
    )

    assert "touched its broker session" in _sites(defects), _sites(defects)


def test_ARM2_REDDENS_when_A_QUIET_RUN_STILL_WROTE_A_MARKER() -> None:
    """Nothing happened, so there is nothing to record."""
    defects = gate.control_defects(
        FakeDrill(
            wakes=tuple(_wake(acted=False, cause=None) for _ in range(20)),
            marker_records=(_rec("after"),),
        )
    )

    assert "wrote 1 marker record" in _sites(defects), _sites(defects)


# ==========================================================================
# ARM 3 — the mid-flatten death
# ==========================================================================


def test_ARM3_REDDENS_when_THE_CHILD_DID_NOT_DIE_WHERE_THE_DRILL_NEEDED_IT() -> None:
    """`MID_FLATTEN_EXIT` is reachable only from inside `flatten_all`. Any other
    code means the process died somewhere else and the arm measured nothing."""
    defects = gate.interrupted_defects(
        FakeDrill(sentinel_returncode=1, marker_records=(_rec("before"),)), 97
    )

    assert "exited 1, not 97" in _sites(defects), _sites(defects)
    assert "measured nothing" in _sites(defects), _sites(defects)


def test_ARM3_REDDENS_when_A_MID_FLATTEN_DEATH_LEFT_NO_RECORD() -> None:
    """A `before` that did not survive means the record was buffered, and
    §12.1:608's whole fix is a record that outlives the process."""
    defects = gate.interrupted_defects(
        FakeDrill(sentinel_returncode=97, marker_records=()), 97
    )

    assert "must hold exactly one 'before'" in _sites(defects), _sites(defects)
    assert "buffered" in _sites(defects), _sites(defects)


def test_ARM3_REDDENS_when_AN_AFTER_RECORD_SURVIVED_A_DEATH_MID_ACT() -> None:
    """An `after` written by a process that died inside `flatten_all` would mean
    the record does not mark the act's boundaries at all."""
    defects = gate.interrupted_defects(
        FakeDrill(
            sentinel_returncode=97, marker_records=(_rec("before"), _rec("after"))
        ),
        97,
    )

    assert "no 'after'" in _sites(defects), _sites(defects)


# ==========================================================================
# ARM 6 — the §14 boundary
# ==========================================================================


def test_ARM6_REDDENS_when_THE_LIMITER_MODULE_STOPS_REFUSING_THE_SENTINEL_TRIGGER(
    monkeypatch,
) -> None:
    """`nixrisk/flatten.py` refuses `SENTINEL` deliberately: §14:977-978 permits
    ONE exception to Limiter-only execution and the live Limiter's own module is
    not it. Removing the refusal must redden."""
    from nixrisk import flatten  # pylint: disable=import-outside-toplevel

    monkeypatch.setattr(flatten, "_R4_TRIGGERS", frozenset())

    defects = gate.refusal_defects()

    assert "rather than TriggerNotFireable" in _sites(defects) or "ACCEPTED" in _sites(
        defects
    ), _sites(defects)


def test_ARM6_REDDENS_when_THE_SENTINEL_IMPORTS_THE_LIMITERS_PACKAGE(
    tmp_path: Path,
) -> None:
    """§12.1:603's separate code path. A shared import graph means the defect that
    killed the Risk Engine also kills its watcher, which is the common-mode
    failure this whole component exists to avoid."""
    pkg = tmp_path / "scripts" / "nixsentinel"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "watchdog.py").write_text("import nixrisk.seam\n", encoding="utf-8")
    risk = tmp_path / "scripts" / "nixrisk"
    risk.mkdir(parents=True)
    (risk / "__init__.py").write_text("", encoding="utf-8")
    (risk / "seam.py").write_text("", encoding="utf-8")

    defects, found = gate.closure_defects(tmp_path)

    assert "nixrisk" in str(found), found
    assert "SEPARATE CODE PATH" in _sites(defects), _sites(defects)


def test_ARM6_REDDENS_when_THE_WATCHDOG_CALLS_AN_UNAUTHORISED_BROKER_VERB(
    tmp_path: Path,
) -> None:
    """A widened session is a widened authority whatever it is called."""
    (tmp_path / "scripts" / "nixsentinel").mkdir(parents=True)
    (tmp_path / gate.WATCHDOG).write_text(
        "class S:\n    def go(self):\n        self._broker.place_order('MES')\n",
        encoding="utf-8",
    )

    defects = gate.verb_defects(tmp_path, ("connect", "open_positions", "flatten_all"))

    assert "self._broker.place_order()" in _sites(defects), _sites(defects)
    assert "not a second execution authority" in _sites(defects), _sites(defects)


def test_ARM6s_AUTHORISED_SET_COMES_FROM_THE_FROZEN_SEAM_and_not_the_watchdog() -> None:
    """The expected side must not be readable out of the file under test, or the
    subject can widen itself — the shape `check_pollers` was measured doing."""
    verbs = gate._authorised_verbs(REPO)

    assert set(verbs) == {"connect", "open_positions", "flatten_all", "disconnect"}
    assert gate.SEAM.endswith("seam.py") and gate.SEAM != gate.WATCHDOG


# ==========================================================================
# ARM 7 — the hint never decides
# ==========================================================================


def test_ARM7_REDDENS_when_A_CONDITIONAL_IN_THE_WATCHDOG_READS_THE_HINT(
    tmp_path: Path,
) -> None:
    """The hint is the last known count of a process dead for at least the loss
    threshold. §4 makes the broker the record."""
    (tmp_path / "scripts" / "nixsentinel").mkdir(parents=True)
    (tmp_path / gate.WATCHDOG).write_text(
        "def go(beat):\n"
        "    if beat.positions_open:\n"
        "        return 'flatten'\n"
        "    return None\n",
        encoding="utf-8",
    )

    defects = gate.branch_defects(tmp_path)

    assert "a conditional reads the heartbeat's `positions_open`" in _sites(defects)
    assert "stale by construction" in _sites(defects), _sites(defects)


def test_ARM7_DOES_NOT_REDDEN_ON_A_NULL_GUARD_that_decides_nothing_about_the_hint(
    tmp_path: Path,
) -> None:
    """The arm's own precision, driven. `beat.positions_open if beat else None`
    tests `beat`, not the hint — and an arm that could not tell those apart would
    push the module toward contortions that make the hazard harder to see. This
    control is here because the first version of the arm reddened on exactly it."""
    (tmp_path / "scripts" / "nixsentinel").mkdir(parents=True)
    (tmp_path / gate.WATCHDOG).write_text(
        "def go(beat):\n    return beat.positions_open if beat else None\n",
        encoding="utf-8",
    )

    assert gate.branch_defects(tmp_path) == []


# ==========================================================================
# ARM 4 / ARM 5 / ARM 8
# ==========================================================================


def test_ARM4_REDDENS_when_THE_INTERRUPTED_RECORD_READS_BACK_EMPTY(
    tmp_path: Path,
) -> None:
    """A `before` with no `after` is the evidence §12.1:608 exists to preserve."""
    defects, rows = gate.replay_defects(tmp_path / "absent.jsonl")

    assert rows == 0
    assert "read back EMPTY" in _sites(defects), _sites(defects)


def test_ARM5_REDDENS_when_APPEND_RETURNS_WITHOUT_SYNCING(
    tmp_path: Path, monkeypatch
) -> None:
    """A marker still in the page cache dies with the process it was written to
    outlive, which is the whole of §12.1:608's fix."""
    import nixsentinel.marker as marker_mod  # pylint: disable=import-outside-toplevel

    class Lazy:
        """A writer that writes and never syncs. The exact defect."""

        def __init__(self, path) -> None:
            self.path = Path(path)
            self.path.parent.mkdir(parents=True, exist_ok=True)

        def append(self, record) -> None:
            """Write, and stop there."""
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"phase": record.phase.value}) + "\n")

    monkeypatch.setattr(marker_mod, "MarkerWriter", Lazy)

    defects, calls = gate.durability_defects(tmp_path / "lazy")

    assert calls == 0
    assert "returned without calling fsync" in _sites(defects), _sites(defects)


def test_ARM8_REDDENS_when_THE_SHIPPED_KNOB_SET_IS_INVALID(tmp_path: Path) -> None:
    """A gate that loaded a broken knob set and called it green would certify a
    deadman with a made-up idea of how long silence means death."""
    shutil.copytree(REPO / "risks", tmp_path / "risks")
    target = tmp_path / "risks" / "sentinel.config.json"
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["heartbeat_loss_multiple"] = 1
    target.write_text(json.dumps(payload), encoding="utf-8")

    defects, driven = gate.knob_defects(tmp_path, tmp_path / "work")

    assert driven == ()
    assert "the shipped knob set is invalid" in _sites(defects), _sites(defects)
    assert "sentinel.loss_outlasts_limiter_grace" in _sites(defects), _sites(defects)


def test_ARM8_DRIVES_EVERY_SENTINEL_BOOT_RULE_RED_on_the_real_tree(
    tmp_path: Path,
) -> None:
    """The floor is not an arithmetic identity: the rules are perturbed one at a
    time against REAL copied files and each must name ITS OWN id."""
    defects, driven = gate.knob_defects(REPO, tmp_path)

    assert defects == [], _sites(defects)
    assert len(driven) >= gate.MIN_DRIVEN_RULES, driven
    assert "sentinel.loss_outlasts_limiter_grace" in driven, driven
    assert "sentinel.poll_fits_loss_threshold" in driven, driven


# ==========================================================================
# THE REFUSALS — an unread subject is CANNOT_MEASURE, never PASS
# ==========================================================================


def test_AN_EMPTY_AUTHORISED_VERB_SET_IS_A_REFUSAL_and_never_agreement() -> None:
    """ARM 6c's expected side is derived from the frozen seam; an empty
    derivation compares every call against nothing."""
    reading = _reading(authorised_verbs=())

    refusal = gate._floor_refusal(reading)

    assert refusal is not None and refusal.status is Status.CANNOT_MEASURE
    assert "empty derivation is a refusal" in refusal.detail, refusal.detail


def test_A_DRILL_THAT_REAPED_NOBODY_IS_A_REFUSAL_and_never_a_pass() -> None:
    """With no kernel status there is nothing for ARM 1 to judge."""
    reading = _reading(kill_status=None)

    refusal = gate._floor_refusal(reading)

    assert refusal is not None and refusal.status is Status.CANNOT_MEASURE
    assert "headline property was not measured" in refusal.detail, refusal.detail


def _reading(**kw) -> gate.Reading:
    """A healthy `Reading` with one field perturbed."""
    base = {
        "killed_pid": 1,
        "kill_status": -signal.SIGKILL,
        "observed_pid": 1,
        "flattened": ("MES",),
        "kill_marker_phases": ("before", "after"),
        "control_wakes": 40,
        "control_causes": 0,
        "control_broker_calls": 0,
        "die_returncode": 97,
        "die_marker_phases": ("before",),
        "replay_rows": 2,
        "fsync_calls": 2,
        "authorised_verbs": ("connect", "open_positions", "flatten_all", "disconnect"),
        "nixrisk_in_closure": (),
        "driven_rules": ("a", "b"),
        "live_wakes": 5,
    }
    base.update(kw)
    return gate.Reading(**base)  # type: ignore[arg-type]


# ==========================================================================
# THE PLANTS REMOVED — the same population, unperturbed, is clean
# ==========================================================================


def test_THE_UNPERTURBED_ARMS_FIND_NOTHING() -> None:
    """§5.1's last step. Without it the suite shows only that a gate can fail."""
    assert gate.kill_defects(_good_kill(), 5) == []
    assert (
        gate.control_defects(
            FakeDrill(wakes=tuple(_wake(acted=False, cause=None) for _ in range(20)))
        )
        == []
    )
    assert (
        gate.interrupted_defects(
            FakeDrill(sentinel_returncode=97, marker_records=(_rec("before"),)), 97
        )
        == []
    )
    assert gate.refusal_defects() == []
    assert gate.branch_defects(REPO) == []
    assert gate.verb_defects(REPO, gate._authorised_verbs(REPO)) == []
    assert gate._floor_refusal(_reading()) is None


def test_ARM1_REDDENS_when_THE_SENTINEL_NEVER_HANDED_ITS_SESSION_BACK() -> None:
    """§12.1:605 gives the Sentinel its OWN broker session. One it never releases
    is one a restarted Risk Engine may find still held, which turns the separation
    the spec asked for into a different collision."""
    outcome = _good_kill()
    outcome.broker_calls = tuple(
        {"verb": verb} for verb in ("connect", "open_positions", "flatten_all")
    )

    defects = gate.kill_defects(outcome, 5)

    assert "give the session back" in _sites(defects), _sites(defects)


def test_ARM1_REDDENS_when_THE_FLATTEN_PRECEDED_THE_POSITION_READ() -> None:
    """A flatten fired before asking the broker what is open is a flatten against
    no observation — §12.1:605's nuisance act with the condition skipped."""
    outcome = _good_kill()
    outcome.broker_calls = tuple(
        {"verb": verb}
        for verb in ("connect", "flatten_all", "open_positions", "disconnect")
    )

    defects = gate.kill_defects(outcome, 5)

    assert "ask the BROKER what is open before deciding" in _sites(defects)


def test_ARM8_REDDENS_when_A_SENTINEL_BOOT_RULE_STOPS_REJECTING(monkeypatch) -> None:
    """The census, not the count. `MIN_DRIVEN_RULES` is a floor on how many
    perturbations were ATTEMPTED; the defect fires when an attempted one failed to
    redden, so the arm cannot be satisfied by an arithmetic identity."""
    import nixsentinel.config as sconfig  # pylint: disable=import-outside-toplevel

    monkeypatch.setattr(
        gate,
        "_driven_rules",
        lambda home, workdir, cfg: (
            ("sentinel.poll_fits_loss_threshold",),
            (
                "sentinel.loss_outlasts_limiter_grace",
                "sentinel.poll_fits_loss_threshold",
            ),
        ),
    )
    assert sconfig.sentinel_rules(), "no sentinel rule exists to be driven"

    defects, driven = gate.knob_defects(REPO, REPO)

    assert driven == ("sentinel.poll_fits_loss_threshold",)
    assert "did not reject a set built to violate them" in _sites(defects)
    assert "sentinel.loss_outlasts_limiter_grace" in _sites(defects), _sites(defects)
