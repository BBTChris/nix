"""ARC 030 / sub-agent B — can-fail suite for `checks/check_ibgateway_expected_schema.py`.

Structure follows `nix_check_contract.md` §5.1: non-vacuity FIRST, then plants
that must FAIL and NAME their field, then the plants removed and the same
tree passing again.

No plant touches `checks/ibgateway_expected.json` in place (doctrine C.8):
every control builds a throwaway `nix_home` under `tmp_path` holding a COPY.
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(REPO / "checks"))

import check_ibgateway_expected_schema as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    (tmp_path / "checks").mkdir(parents=True)
    shutil.copy(REPO / gate.EXPECTED_FILE, tmp_path / gate.EXPECTED_FILE)
    return tmp_path


def _run(nix_home: Path):
    return gate.run(Mode.VERIFY, Context(nix_home=nix_home, mode=Mode.VERIFY))


def _write(home: Path, data: dict) -> None:
    (home / gate.EXPECTED_FILE).write_text(json.dumps(data), encoding="utf-8")


def _real(home: Path) -> dict:
    return json.loads((home / gate.EXPECTED_FILE).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# NON-VACUITY FIRST
# --------------------------------------------------------------------------


def test_the_REAL_TREE_passes() -> None:
    result = _run(REPO)

    assert result.status is Status.PASS, result
    assert "required key(s) checked" in result.evidence, result.evidence


def test_the_GATE_DECLARES_the_file_as_a_SUBJECT_so_coverage_is_real() -> None:
    assert gate.EXPECTED_FILE in gate.SUBJECTS, gate.SUBJECTS


# --------------------------------------------------------------------------
# PLANTS — one field at a time
# --------------------------------------------------------------------------


def test_a_MISSING_KEY_fails_and_NAMES_it(home: Path) -> None:
    data = _real(home)
    del data["api_port"]
    _write(home, data)

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "api_port" in result.detail, result.detail


def test_a_BAD_API_HOST_fails_and_NAMES_the_field(home: Path) -> None:
    data = _real(home)
    data["api_host"] = "not-an-ip"
    _write(home, data)

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "api_host" in result.site, result.site


def test_an_OUT_OF_RANGE_PORT_fails(home: Path) -> None:
    data = _real(home)
    data["api_port"] = 99999
    _write(home, data)

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "api_port" in result.site, result.site


def test_the_JTS_SSL_TUNNEL_PORT_fails_and_NAMES_the_confusion(home: Path) -> None:
    data = _real(home)
    data["api_port"] = 4000
    _write(home, data)

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "SSL tunnel" in result.detail, result.detail


def test_an_EMPTY_TRUSTED_IPS_fails(home: Path) -> None:
    data = _real(home)
    data["trusted_ips"] = []
    _write(home, data)

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "trusted_ips" in result.site, result.site


def test_a_NON_BOOL_FLAG_fails(home: Path) -> None:
    data = _real(home)
    data["auto_restart"] = "yes"
    _write(home, data)

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "auto_restart" in result.site, result.site


def test_a_MALFORMED_DISPLAY_fails(home: Path) -> None:
    data = _real(home)
    data["display"] = "99"
    _write(home, data)

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "display" in result.site, result.site


def test_a_BAD_UNIT_NAME_fails(home: Path) -> None:
    data = _real(home)
    data["units"] = ["nix-ibgateway"]  # missing .service
    _write(home, data)

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "units" in result.site, result.site


def test_MALFORMED_JSON_fails_and_NAMES_the_parse_error(home: Path) -> None:
    (home / gate.EXPECTED_FILE).write_text("{not json", encoding="utf-8")

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "not valid JSON" in result.detail, result.detail


# --------------------------------------------------------------------------
# THE THIRD STEP — plant removed, the same tree passing again
# --------------------------------------------------------------------------


def test_a_PLANT_APPLIED_AND_REVERTED_leaves_the_gate_GREEN_on_the_same_tree(
    home: Path,
) -> None:
    before = (home / gate.EXPECTED_FILE).read_bytes()
    data = _real(home)
    data["api_port"] = 4000
    _write(home, data)

    planted = _run(home)
    (home / gate.EXPECTED_FILE).write_bytes(before)
    restored = _run(home)

    assert planted.status is Status.FAIL_NEEDS_OPERATOR, planted
    assert restored.status is Status.PASS, restored
    assert (home / gate.EXPECTED_FILE).read_bytes() == before, (
        "the control was not restored"
    )


# --------------------------------------------------------------------------
# CANNOT_MEASURE, never PASS
# --------------------------------------------------------------------------


def test_an_ABSENT_FILE_is_CANNOT_MEASURE(home: Path) -> None:
    (home / gate.EXPECTED_FILE).unlink()

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "absent" in result.detail, result.detail
