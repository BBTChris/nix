"""ARC 034 / sub-agent C — the can-fail suite for `checks/check_orphan_recovery.py`.

Structure follows the `check_flatten` precedent (`nix_check_contract.md` §5.1):
non-vacuity FIRST (the real tree passes and the evidence carries the OBSERVED
step sequence), then plants that must FAIL and NAME their site.

**No plant touches a production artifact** (doctrine C.8). Every control builds a
throwaway `nix_home` under `tmp_path` holding COPIES of the subject and its
collaborators, perturbs the COPY, and drives the SHIPPED gate's own bytes
against it. `scripts/nixrisk/recovery.py` is read and never written here.

THE PLANT THAT MATTERS is the one that reverses the EXECUTION ORDER while
leaving all three calls in the file. If the gate could not redden on that, its
whole subject would be unmeasured — so it is the first plant below and it
asserts the ORPHANING, not merely a different list.

Every `§` cites `docs/nics_risk_subsystem_spec_v1.3.md` unless another document
is named on the same line.
"""

# pylint: disable=invalid-name,redefined-outer-name,duplicate-code

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.append(str(REPO / "checks"))

import check_orphan_recovery as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)

NIXRISK = (
    "__init__.py",
    "recovery.py",
    "supervision.py",
    "flatten.py",
    "picture.py",
    "reservations.py",
    "gate.py",
    "halt.py",
    "seam.py",
)
NIXALLOC = ("__init__.py", "lifecycle.py", "seam.py", "mirror.py", "contention.py")
OTHER = ("scripts/risk_config.py",)
#: DERIVED, not enumerated, and the change is a measured one. This tuple used to
#: name five configs by hand and was correct for the tree it was written against;
#: ARC 034's sub-agent B then added `risks/sentinel.config.json` and widened
#: `risk_config.OWNED_MODULES` in a parallel worktree, so on the MERGED tree the
#: scratch home was missing a config the validator requires and the CONTROL went
#: CANNOT_MEASURE before a single plant had been applied — eleven red tests, none
#: of them about this gate's subject.
#:
#: The authority for which configs must exist is `risk_config.OWNED_MODULES`, not
#: a list in a test file. This is deliberately NOT the self-agreement shape §0a
#: warns about: nothing here is asserted against, it is only what gets copied into
#: the venue, so the gate's findings stay independent of it.
RISKS = tuple(path.name for path in sorted((REPO / "risks").glob("*.json")))


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """A throwaway tree carrying COPIES of the sequencer and its collaborators."""
    (tmp_path / "scripts" / "nixrisk").mkdir(parents=True)
    (tmp_path / "scripts" / "nixalloc").mkdir(parents=True)
    (tmp_path / "scripts" / "broker").mkdir(parents=True)
    (tmp_path / "risks").mkdir(parents=True)
    for name in NIXRISK:
        shutil.copy(
            REPO / "scripts" / "nixrisk" / name, tmp_path / "scripts" / "nixrisk" / name
        )
    for name in NIXALLOC:
        shutil.copy(
            REPO / "scripts" / "nixalloc" / name,
            tmp_path / "scripts" / "nixalloc" / name,
        )
    for rel in OTHER:
        shutil.copy(REPO / rel, tmp_path / rel)
    for name in RISKS:
        shutil.copy(REPO / "risks" / name, tmp_path / "risks" / name)
    return tmp_path


def _run(nix_home: Path):
    return gate.run(Mode.VERIFY, Context(nix_home=nix_home, mode=Mode.VERIFY))


def _plant(
    home: Path, old: str, new: str, rel: str = "scripts/nixrisk/recovery.py"
) -> None:
    path = home / rel
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"anchor appears {text.count(old)} times, not once"
    path.write_text(text.replace(old, new), encoding="utf-8")


def _red(result, *, site: str, phrase: str) -> None:
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert site in (result.site or ""), result.site
    assert phrase in (result.detail or ""), result.detail


# --------------------------------------------------------------------------
# NON-VACUITY FIRST
# --------------------------------------------------------------------------


def test_the_REAL_TREE_passes_and_the_EVIDENCE_carries_the_OBSERVED_SEQUENCE() -> None:
    """Non-vacuity first: the shipped tree is green and the evidence PRINTS the
    sequence that actually executed, in the order it executed."""
    result = _run(REPO)

    assert result.status is Status.PASS, result
    assert "THE OBSERVED STEP SEQUENCE" in result.evidence, result.evidence
    assert "'flatten'" in result.evidence, result.evidence
    assert "'force_deregister'" in result.evidence, result.evidence
    flatten_at = result.evidence.index("'flatten'")
    dereg_at = result.evidence.index("'force_deregister'")
    assert flatten_at < dereg_at, (
        "the evidence prints the observed sequence in the wrong order"
    )
    # RE-POINTED ARC 037 (CHECK-DEBT D3.252/D3.306): the boundary used to read
    # "ARC R5 … Scoring does not exist in this tree", which stopped being true
    # when scripts/nixscore/ landed. What is absent now is the JOIN.
    assert "NO JOIN" in result.evidence, "the scoring boundary is not printed"
    assert "ScoreStore.archive_strategy" in result.evidence, result.evidence


def test_the_COPIED_TREE_also_passes_so_every_plant_below_starts_GREEN(
    home: Path,
) -> None:
    """A plant that reddens a tree that was already red measures the fixture."""
    assert _run(home).status is Status.PASS, _run(home)


def test_the_GATE_DECLARES_the_recovery_module_as_a_SUBJECT() -> None:
    """The artifact-coverage ratchet FAILs on an artifact no check declares."""
    assert "scripts/nixrisk/recovery.py" in gate.SUBJECTS, gate.SUBJECTS
    assert gate.CORRECTABLE is False
    assert gate.NON_CORRECTABLE_REASON


# --------------------------------------------------------------------------
# PLANT 1 — THE ORDER REVERSED. The plant this gate exists for.
# --------------------------------------------------------------------------


def test_a_DEREGISTER_FIRST_SEQUENCER_fails_and_NAMES_the_orphaning(
    home: Path,
) -> None:
    """All three calls stay in the file; only the EXECUTION order changes. This
    is the mistake source-order review cannot catch, and the reason the journal
    exists at all."""
    _plant(
        home,
        "        flattened = self._step_flatten(strategy_id, stamp)\n"
        "        version = self._step_publish(strategy_id, stamp)\n"
        "        dereg = self._step_deregister(strategy_id, stamp)",
        "        dereg = self._step_deregister(strategy_id, stamp)  # PLANTED FIRST\n"
        "        flattened = self._step_flatten(strategy_id, stamp)\n"
        "        version = self._step_publish(strategy_id, stamp)",
    )

    result = _run(home)

    _red(result, site="order", phrase="flattens FIRST and force-deregisters SECOND")
    assert "orphans the position" in (result.detail or "")


def test_a_SILENTLY_SKIPPED_FLATTEN_fails_even_though_the_CALL_IS_STILL_THERE(
    home: Path,
) -> None:
    """The other way an order survives review and dies in execution: the call
    site is untouched and the work inside it is guarded away. The journal shows
    the step ran and closed nothing; the non-vacuity assertion catches it."""
    _plant(
        home,
        "        registered = self._registry.is_registered(strategy_id)\n"
        "        rows = self.owned_rows(strategy_id)",
        "        registered = self._registry.is_registered(strategy_id)\n"
        "        rows = ()  # PLANTED: the sweep finds nothing, silently",
    )

    result = _run(home)

    _red(result, site="order", phrase="the order would hold vacuously")


# --------------------------------------------------------------------------
# PLANT 2 — the heartbeat
# --------------------------------------------------------------------------


def test_a_MONITOR_THAT_KILLS_ON_THE_FIRST_MISS_fails(home: Path) -> None:
    """§4:260 waits EXACTLY one cycle. A death flattens positions, so a monitor
    that kills on one dropped beat closes a LIVE strategy's trades."""
    _plant(
        home,
        "        dead = misses > self._grace",
        "        dead = misses >= 1  # PLANTED: one miss is death",
    )

    result = _run(home)

    _red(result, site="heartbeat", phrase="§4:260 waits EXACTLY")


def test_a_MONITOR_WHOSE_BEAT_DOES_NOT_RESET_THE_RUN_fails(home: Path) -> None:
    """CONSECUTIVE is the load-bearing word: miss → beat → miss is a LIVE
    strategy, and a monitor written against an elapsed gap cannot tell it from
    two consecutive misses."""
    _plant(
        home,
        "        self._last[strategy_id] = self._clock() if now is None else float(now)\n"
        "        self._misses[strategy_id] = 0\n\n"
        "    def miss(",
        "        self._last[strategy_id] = self._clock() if now is None else float(now)\n"
        "        # PLANTED: the beat no longer resets the consecutive-miss run\n\n"
        "    def miss(",
    )

    result = _run(home)

    _red(result, site="heartbeat", phrase="the two misses are not CONSECUTIVE")


# --------------------------------------------------------------------------
# PLANT 3 — the teardown
# --------------------------------------------------------------------------


def test_a_PARTIAL_TEARDOWN_fails_and_NAMES_WHICH_of_the_four_survived(
    home: Path,
) -> None:
    """§4:266-268 — 'nothing stale may survive the death'. Leaving the slot held
    is the case a boolean 'deregistered: yes' would hide."""
    _plant(
        home,
        "        freed = row.slot",
        "        freed = None  # PLANTED: the slot is never reported freed",
    )

    result = _run(home)

    _red(result, site="force-deregister", phrase="slot was not torn down")


def test_a_TEARDOWN_THAT_LEAVES_THE_HEARTBEAT_ARMED_fails(home: Path) -> None:
    """§4:267 verbatim: 'a lingering registration would leave the Limiter
    expecting heartbeats / holding a slot'."""
    _plant(
        home,
        "        self._heartbeat.disarm(strategy_id)",
        "        pass  # PLANTED: still expecting heartbeats from a dead strategy",
    )

    result = _run(home)

    _red(result, site="force-deregister", phrase="still watches the dead strategy")


# --------------------------------------------------------------------------
# PLANT 4 — the Allocator reflection
# --------------------------------------------------------------------------


def test_a_RECOVERY_THAT_NEVER_PUBLISHES_IN_FLIGHT_CLOSING_fails(home: Path) -> None:
    """§4:284-286 — a strategy mid-recovery must never read as
    normal-and-available. Without the transitional publish the Allocator would
    hand new capital to a dying strategy."""
    _plant(
        home,
        "                _closing(row) if row.strategy_id == strategy_id else row",
        "                row  # PLANTED: the dying strategy keeps reading OPEN",
    )

    result = _run(home)

    _red(result, site="allocator", phrase="still reads eligible")


def test_a_RECOVERY_THAT_CLOSES_EVERYONES_ROWS_fails_the_NON_VACUITY_FLOOR(
    home: Path,
) -> None:
    """The floor that is NOT an arithmetic identity: a publish that marked EVERY
    row closing would satisfy the assertion above and make the Allocator refuse
    the whole platform."""
    _plant(
        home,
        "                _closing(row) if row.strategy_id == strategy_id else row",
        "                _closing(row)  # PLANTED: everyone is dying",
    )

    result = _run(home)

    _red(result, site="allocator", phrase="was ALSO refused off the same snapshot")


# --------------------------------------------------------------------------
# PLANT 5 — the crash-loop cap
# --------------------------------------------------------------------------


def test_a_RECOVERY_THAT_RELAUNCHES_PAST_THE_CAP_fails(home: Path) -> None:
    """§4:272 — 'after 3 restarts within a window, stop relaunching'."""
    _plant(
        home,
        "        allowed, why = self._breaker.may_relaunch(strategy_id)",
        "        allowed, why = True, 'PLANTED: the cap is ignored'",
    )

    result = _run(home)

    _red(result, site="quarantine", phrase="relaunched instead of quarantining")


def test_a_QUARANTINE_THAT_ALSO_SKIPS_THE_KILL_fails(home: Path) -> None:
    """§4:272 says stop RELAUNCHING, not stop killing. A half-dead process left
    alive is the orphan state the whole rule exists to end."""
    _plant(
        home,
        "        killed = self._supervisor.kill(strategy_id)",
        "        killed = 'PLANTED: not killed'",
    )

    result = _run(home)

    _red(result, site="quarantine", phrase="did not KILL")


# --------------------------------------------------------------------------
# The gate's own failure modes
# --------------------------------------------------------------------------


def test_a_MISSING_SUBJECT_is_CANNOT_MEASURE_and_never_a_PASS(tmp_path: Path) -> None:
    """§17: a safety property proven while its subject is unavailable is not
    proven. The absence must NEVER read as green."""
    result = _run(tmp_path)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "cannot load the §4 recovery subject" in (result.detail or "")


def test_no_plant_touched_the_repository() -> None:
    """Doctrine C.8, asserted rather than promised: the live tree is still green."""
    assert _run(REPO).status is Status.PASS
