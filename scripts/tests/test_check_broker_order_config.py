"""ARC 030 / sub-agent B — the can-fail suite for `checks/check_broker_order_config.py`.

Structure follows `nix_check_contract.md` §5.1: non-vacuity FIRST, then plants
that must FAIL and NAME their rule tag, then the plants removed and the same
tree passing again.

**No plant touches a production artifact** (doctrine C.8): the gate itself
writes every plant to a `tempfile` copy; this suite additionally never edits
`risks/broker_order.config.json` or `risks/limiter.config.json` in place —
every control builds a throwaway `nix_home` under `tmp_path` holding COPIES.
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.append(str(REPO / "checks"))

import check_broker_order_config as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)

FILES = (
    "risks/broker_order.config.json",
    "risks/limiter.config.json",
    "scripts/broker/broker_order_config.py",
    "scripts/broker/broker_seam.py",
)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    (tmp_path / "risks").mkdir(parents=True)
    (tmp_path / "scripts" / "broker").mkdir(parents=True)
    for rel in FILES:
        shutil.copy(REPO / rel, tmp_path / rel)
    return tmp_path


def _run(nix_home: Path):
    return gate.run(Mode.VERIFY, Context(nix_home=nix_home, mode=Mode.VERIFY))


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


# --------------------------------------------------------------------------
# NON-VACUITY FIRST
# --------------------------------------------------------------------------


def test_the_REAL_TREE_passes() -> None:
    result = _run(REPO)

    assert result.status is Status.PASS, result
    assert "5 plants" in result.evidence, result.evidence


def test_the_GATE_DECLARES_the_config_as_a_SUBJECT_so_coverage_is_real() -> None:
    assert gate.CONFIG_FILE in gate.SUBJECTS, gate.SUBJECTS
    assert gate.CORRECTABLE is False
    assert gate.NON_CORRECTABLE_REASON


# --------------------------------------------------------------------------
# PLANT 1 — negative scalar (positive.scalars)
# --------------------------------------------------------------------------


def test_a_NEGATIVE_SCALAR_fails_and_NAMES_positive_scalars(home: Path) -> None:
    cfg = json.loads((home / gate.CONFIG_FILE).read_text())
    cfg["flatten_idempotency_window_ms"] = -5
    _write_json(home / gate.CONFIG_FILE, cfg)

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "positive.scalars" in result.detail, result.detail


# --------------------------------------------------------------------------
# PLANT 2 — flatten window exceeds pending-ack timeout
# --------------------------------------------------------------------------


def test_a_FLATTEN_WINDOW_TOO_WIDE_fails_and_NAMES_the_ordering_rule(
    home: Path,
) -> None:
    cfg = json.loads((home / gate.CONFIG_FILE).read_text())
    limiter = json.loads((home / gate.LIMITER_FILE).read_text())
    cfg["flatten_idempotency_window_ms"] = (
        int(limiter["pending_ack_timeout_ms"]) + 999_999
    )
    _write_json(home / gate.CONFIG_FILE, cfg)

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "ordering.flatten_window_within_pending_ack" in result.detail, result.detail


# --------------------------------------------------------------------------
# PLANT 3 — a required key removed
# --------------------------------------------------------------------------


def test_a_MISSING_REQUIRED_KEY_fails_and_NAMES_it(home: Path) -> None:
    cfg = json.loads((home / gate.CONFIG_FILE).read_text())
    del cfg["flatten_attempt_log_depth"]
    _write_json(home / gate.CONFIG_FILE, cfg)

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "flatten_attempt_log_depth" in result.detail, result.detail


# --------------------------------------------------------------------------
# THE THIRD STEP — plants removed, the same tree passing again
# --------------------------------------------------------------------------


def test_a_PLANT_APPLIED_AND_REVERTED_leaves_the_gate_GREEN_on_the_same_tree(
    home: Path,
) -> None:
    before = (home / gate.CONFIG_FILE).read_bytes()
    cfg = json.loads(before)
    cfg["flatten_idempotency_window_ms"] = -5
    _write_json(home / gate.CONFIG_FILE, cfg)

    planted = _run(home)
    (home / gate.CONFIG_FILE).write_bytes(before)
    restored = _run(home)

    assert planted.status is Status.FAIL_NEEDS_OPERATOR, planted
    assert restored.status is Status.PASS, restored
    assert (home / gate.CONFIG_FILE).read_bytes() == before, (
        "the control was not restored"
    )


# --------------------------------------------------------------------------
# CANNOT_MEASURE, never PASS
# --------------------------------------------------------------------------


def test_an_ABSENT_CONFIG_is_CANNOT_MEASURE(home: Path) -> None:
    (home / gate.CONFIG_FILE).unlink()

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "absent" in result.detail, result.detail


def test_the_GATE_LEAVES_THE_INTERPRETER_AS_IT_FOUND_IT(home: Path) -> None:
    real = sys.modules.get("broker_order_config")
    paths_before = list(sys.path)

    _run(home)

    assert sys.path == paths_before, "the gate leaked a sys.path entry"
    assert sys.modules.get("broker_order_config") is real, (
        "the gate left the tmp_path copy of broker_order_config in sys.modules"
    )
