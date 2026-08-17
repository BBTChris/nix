"""ARC 033 / Stage 1 / D — the can-fail suite for `checks/check_halt.py`.

Structure follows `nix_check_contract.md` §5.1 and the sibling suites: non-vacuity
FIRST, then plants that must FAIL and NAME their site, then the same tree passing
again with the plants removed.

**No plant touches a production artifact** (doctrine C.8): every control builds a
throwaway `nix_home` under `tmp_path` holding COPIES of the whole `nixrisk`
package, the shipped limiter config and the frozen risk spec, perturbs the COPY,
and drives the SHIPPED gate's own bytes against it.

Every assertion names the REASON, never the status alone (check contract v2 §11):
an exit code and a `Status` are shared namespaces, and a gate that reddened
because its subject failed to import looks identical to one that caught the plant.
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# pylint: disable=missing-function-docstring
# Each test's NAME states the property it drives; a docstring would restate it.

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.append(str(REPO / "checks"))

import check_halt as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)

SPEC_REL = "docs/nics_risk_subsystem_spec_v1.3.md"
CONFIG_REL = "risks/limiter.config.json"


@pytest.fixture
def home(tmp_path: Path) -> Path:
    shutil.copytree(
        REPO / "scripts" / "nixrisk",
        tmp_path / "scripts" / "nixrisk",
        ignore=shutil.ignore_patterns(
            "__pycache__", ".git", ".venv", ".venv-dev", "*.pyc", "graphify-out"
        ),
    )
    (tmp_path / "docs").mkdir()
    (tmp_path / "risks").mkdir()
    shutil.copy(REPO / SPEC_REL, tmp_path / SPEC_REL)
    shutil.copy(REPO / CONFIG_REL, tmp_path / CONFIG_REL)
    return tmp_path


def _run(nix_home: Path):
    return gate.run(Mode.VERIFY, Context(nix_home=nix_home, mode=Mode.VERIFY))


def _plant(home: Path, rel: str, old: str, new: str) -> None:
    path = home / rel
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"anchor appears {text.count(old)} times, not once"
    path.write_text(text.replace(old, new), encoding="utf-8")


def _halt(home: Path, old: str, new: str) -> None:
    _plant(home, gate.HALT_FILE, old, new)


def _red(result, *, site: str, phrase: str) -> None:
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert site in result.site, result.site
    assert phrase in result.detail, result.detail


# --------------------------------------------------------------------------
# NON-VACUITY FIRST
# --------------------------------------------------------------------------


def test_the_REAL_TREE_passes_and_the_EVIDENCE_names_the_ARMS() -> None:
    result = _run(REPO)

    assert result.status is Status.PASS, result
    for phrase in (
        "six setters",
        "operator-only clear",
        "Plane 2 only",
        "GENUINE SIGKILL",
        "7 arms",
    ):
        assert phrase in result.evidence, result.evidence


def test_the_COPIED_TREE_passes_so_every_PLANT_below_is_the_only_difference(
    home: Path,
) -> None:
    result = _run(home)

    assert result.status is Status.PASS, result


def test_the_GATE_DECLARES_halt_as_a_SUBJECT_so_coverage_is_real() -> None:
    assert gate.HALT_FILE in gate.SUBJECTS, gate.SUBJECTS
    assert gate.CORRECTABLE is False
    assert gate.NON_CORRECTABLE_REASON


def test_an_ABSENT_SUBJECT_is_CANNOT_MEASURE_and_never_a_PASS(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()

    result = _run(tmp_path)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "nothing was measured" in result.detail or "OUTSIDE" in result.detail


# --------------------------------------------------------------------------
# PLANT 1 — the operator asymmetry removed (operator becomes auto-clearable)
# --------------------------------------------------------------------------


def test_an_AUTO_CLEARABLE_OPERATOR_HALT_fails_and_NAMES_the_asymmetry(
    home: Path,
) -> None:
    _halt(
        home,
        "        return self is not HaltCause.OPERATOR",
        "        return True  # PLANTED: operator HALT may auto-clear",
    )

    result = _run(home)

    _red(result, site="setters", phrase="auto_clearable")


# --------------------------------------------------------------------------
# PLANT 2 — the §12.5:632 floor dropped from the eligibility arithmetic
# --------------------------------------------------------------------------


def test_a_DROPPED_COOLDOWN_FLOOR_fails_and_NAMES_the_early_clear(home: Path) -> None:
    _halt(
        home,
        "        return max(record.set_ts, record.condition_cleared_ts) + self._floors[cause]",
        "        return max(record.set_ts, record.condition_cleared_ts)  # PLANTED",
    )

    result = _run(home)

    _red(result, site="auto_clear", phrase="before the floor elapsed")


# --------------------------------------------------------------------------
# PLANT 3 — the §3:173 onset sweep never runs
# --------------------------------------------------------------------------


def test_an_ONSET_THAT_CANCELS_NOTHING_fails_and_NAMES_the_pending_entries(
    home: Path,
) -> None:
    _halt(
        home,
        "            swept = self._sweep_pending_entries()",
        "            swept = False  # PLANTED: the onset sweep never runs",
    )

    result = _run(home)

    _red(result, site="entry_not_exit", phrase="cancels every pending ENTRY order")


# --------------------------------------------------------------------------
# PLANT 4 — the marker written AFTER the row instead of before
# --------------------------------------------------------------------------


def test_a_MARKER_WRITTEN_TOO_LATE_fails_the_LIMITER_DOWN_arm(home: Path) -> None:
    _halt(
        home,
        # ARC 034 (D3.195): the anchor gained `self._boot_id` when `(boot, seq)`
        # replaced `seq` as the marker record identity.
        "            self._marker.record_set(cause, detail, stamp, seq, self._boot_id)",
        "            pass  # PLANTED: nothing recorded before the row is booked",
    )

    result = _run(home)

    _red(result, site="limiter_down", phrase="marker `set` record")


# --------------------------------------------------------------------------
# PLANT 5 — a retroactive booking that a reader cannot tell from a live one
# --------------------------------------------------------------------------


def test_an_UNTAGGED_REPLAY_fails_and_NAMES_the_indistinguishable_row(
    home: Path,
) -> None:
    _halt(
        home,
        '                "source": SOURCE_REPLAY,',
        '                "source": SOURCE_LIVE,  # PLANTED: replay looks live',
    )

    result = _run(home)

    _red(result, site="limiter_down", phrase="retroactive booking from a live one")


# --------------------------------------------------------------------------
# PLANT 6 — the replay stamps the row with the BOOT time
# --------------------------------------------------------------------------


def test_a_REPLAY_STAMPED_AT_BOOT_fails_and_NAMES_the_moved_event(home: Path) -> None:
    _halt(
        home,
        "            ts=entry.ts,\n            strategy_id=SYSTEM_ACTOR,",
        "            ts=now,  # PLANTED: the outage moves the event\n"
        "            strategy_id=SYSTEM_ACTOR,",
    )

    result = _run(home)

    _red(result, site="limiter_down", phrase="not the declare")


# --------------------------------------------------------------------------
# PLANT 7 — the boot validation stops refusing an operator floor
# --------------------------------------------------------------------------


def test_an_ACCEPTED_OPERATOR_FLOOR_fails_because_the_FALSIFIER_stops_falsifying(
    home: Path,
) -> None:
    _halt(
        home,
        "    unknown = sorted(set(floors) - set(admissible))",
        "    unknown = []  # PLANTED: any key accepted",
    )

    result = _run(home)

    _red(result, site="setters:falsifier", phrase="was ACCEPTED")


# --------------------------------------------------------------------------
# PLANT 8 — §12.10's own table says something else
# --------------------------------------------------------------------------


def test_a_SPEC_ROW_THAT_DROPS_PLANE_1_fails_and_NAMES_the_routing(
    home: Path,
) -> None:
    _plant(
        home,
        SPEC_REL,
        "| HALT set / cleared + cause | ✅ *(added — it gates money; "
        "Limiter-down ⇒ booked at next boot, §12.5)* | ✅ |",
        "| HALT set / cleared + cause | — | ✅ |",
    )

    result = _run(home)

    _red(result, site="planes", phrase="BOTH planes ticked")


# --------------------------------------------------------------------------
# PLANT 9 — an AWAITED artifact appears, so a "no producer" claim may be stale
# --------------------------------------------------------------------------


def test_an_AWAITED_ARTIFACT_APPEARING_fails_so_the_claim_is_RE_MEASURED(
    home: Path,
) -> None:
    # ARC 034 moved `CRASH_LOOP` out of AWAITED (supervision LANDED), so the
    # plant moved to a cause that is still awaited. §12.11's authenticated
    # operator transport is the one nothing in flight is building.
    (home / "scripts" / "nixrisk" / "operator.py").write_text(
        '"""PLANTED: §12.11 operator transport lands."""\n', encoding="utf-8"
    )

    result = _run(home)

    _red(result, site="producers", phrase="may now have one")


# --------------------------------------------------------------------------
# PLANT 10 — the R4-B deferral removed from the subject
# --------------------------------------------------------------------------


def test_a_REMOVED_R4B_DEFERRAL_fails_because_the_gate_would_imply_coverage(
    home: Path,
) -> None:
    _halt(
        home,
        "* **The Sentinel deadman (§12.1) is NOT built. It is R4-B.**",
        "* The Sentinel is handled.",
    )

    result = _run(home)

    _red(result, site="producers", phrase="implies coverage it does not have")


# --------------------------------------------------------------------------
# THE PLANTS REMOVED — the same tree passes again
# --------------------------------------------------------------------------


def test_the_SAME_TREE_passes_once_a_PLANT_is_REVERTED(home: Path) -> None:
    path = home / gate.HALT_FILE
    original = path.read_text(encoding="utf-8")
    _halt(
        home,
        "        return self is not HaltCause.OPERATOR",
        "        return True  # PLANTED",
    )
    assert _run(home).status is Status.FAIL_NEEDS_OPERATOR

    path.write_text(original, encoding="utf-8")

    assert _run(home).status is Status.PASS
