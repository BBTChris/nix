"""The can-fail suite for `checks/check_nonblocking_send.py` (Module 2, B6).

Structure follows `nix_check_contract.md` §5.1 — *plant BOTH*: non-vacuity
FIRST, then one plant per arm, each of which must FAIL and must **NAME the
reason** (check contract rule 11: assert the message, never the exit code and
never merely `status != PASS`), then the plants removed and the same tree
passing again.

**NO PLANT TOUCHES A PRODUCTION ARTIFACT** (doctrine C.8). Every control builds
a throwaway `nix_home` under `tmp_path` holding COPIES of the five files the
gate reads, and `test_the_PRODUCTION_TREE_is_byte_identical_afterwards` asserts
that `scripts/broker/*.py` is unchanged once the whole suite has run.

WHY EACH PLANT IS THE PLANT IT IS — the discrimination is the point:

  * `time.sleep(0)` in `place_order` is caught by the STRUCTURAL arm ONLY: it
    sleeps for zero seconds, so no budget could ever see it.
  * a busy-wait in `flatten` is caught by the TIMED arm ONLY: a `while` loop
    over `time.monotonic()` contains no banned construct, so the AST walk is
    silent about it.

Two plants that are each invisible to the other arm are what proves both arms
are live. A single plant both arms caught would leave either one able to be
switched off unnoticed.
"""

# pylint: disable=missing-function-docstring,missing-module-docstring
# pylint: disable=use-implicit-booleaness-not-comparison
# Same rulings as test_check_broker_seam_identity.py.
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code

from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.append(str(REPO / "checks"))

import check_nonblocking_send as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)

FILES = (
    "risks/broker_order.config.json",
    "risks/limiter.config.json",
    "scripts/broker/broker_seam.py",
    "scripts/broker/broker_order_ibkr.py",
    "scripts/broker/broker_order_config.py",
)

PRODUCTION_FILES = tuple(rel for rel in FILES if rel.endswith(".py"))

# The anchors every plant is written against. Each is asserted PRESENT before
# it is used, so a plant that silently applied to nothing — and therefore
# tested nothing — is impossible (debug.md §8 failure mode #4: an anchor that
# has moved must be loud, not quiet).
ANCHOR_PLACE = '        self._require_session("place_order")'
ANCHOR_FLATTEN = '        self._require_session("flatten")'
ANCHOR_DISCONNECT = "        self._connected = False\n        # Close the gate too:"
ANCHOR_IMPORTS = "import itertools"
ANCHOR_LOG = 'log = logging.getLogger("nix.broker_order.ibkr")'
ANCHOR_CAVEAT = "ZERO bytes"

#: Long enough to blow `NONBLOCKING_BUDGET_S` unambiguously, short enough that
#: the suite stays quick. Derived from the constant so the two cannot drift.
SPIN_S = gate.NONBLOCKING_BUDGET_S + 0.1


@pytest.fixture
def home(tmp_path: Path) -> Path:
    (tmp_path / "risks").mkdir(parents=True)
    (tmp_path / "scripts" / "broker").mkdir(parents=True)
    for rel in FILES:
        shutil.copy(REPO / rel, tmp_path / rel)
    return tmp_path


def _run(nix_home: Path):
    return gate.run(Mode.VERIFY, Context(nix_home=nix_home, mode=Mode.VERIFY))


def _adapter(nix_home: Path) -> Path:
    return nix_home / gate.ADAPTER_FILE


def _patch(nix_home: Path, old: str, new: str) -> None:
    """Rewrite the adapter COPY, refusing to plant against a missing anchor."""
    path = _adapter(nix_home)
    text = path.read_text(encoding="utf-8")
    assert old in text, (
        f"plant anchor has moved and the plant would test nothing: {old!r}"
    )
    path.write_text(text.replace(old, new), encoding="utf-8")


def _add_threading(nix_home: Path) -> None:
    _patch(
        nix_home, ANCHOR_IMPORTS, f"{ANCHOR_IMPORTS}\nimport threading as _threading"
    )
    _patch(nix_home, ANCHOR_LOG, f"{ANCHOR_LOG}\n_planted_lock = _threading.Lock()")


# --------------------------------------------------------------------------
# NON-VACUITY FIRST
# --------------------------------------------------------------------------


def test_the_REAL_TREE_passes() -> None:
    result = _run(REPO)

    assert result.status is Status.PASS, result
    # The gate PASSED having actually walked and actually driven — the two
    # facts an empty instrument could not produce.
    assert "walked 5 send verb(s)" in result.evidence, result.evidence
    assert "IBKRBrokerOrder.flatten" in result.evidence, result.evidence
    assert "0 delivered" in result.evidence, result.evidence
    assert gate.DELIVERY_CAVEAT in result.evidence, result.evidence


def test_a_COPY_of_the_tree_passes_so_every_plant_below_starts_GREEN(
    home: Path,
) -> None:
    result = _run(home)

    assert result.status is Status.PASS, result


def test_the_GATE_DECLARES_its_subjects_and_its_non_correctability() -> None:
    assert gate.ADAPTER_FILE in gate.SUBJECTS, gate.SUBJECTS
    assert gate.SEAM_FILE in gate.SUBJECTS, gate.SUBJECTS
    assert gate.CORRECTABLE is False
    assert gate.NON_CORRECTABLE_REASON
    assert gate.TIME_BOUND is True
    assert gate.DEPENDS_ON == ()


def test_the_SEND_VERB_SET_is_DERIVED_from_the_seam_and_not_typed(home: Path) -> None:
    """The roster is read out of `broker_seam.py`; gut it and the gate goes blind."""
    seam = home / gate.SEAM_FILE
    text = seam.read_text(encoding="utf-8")
    assert "ORDER_PORT_VERBS: tuple[str, ...] = (" in text
    seam.write_text(
        text.replace(
            "ORDER_PORT_VERBS: tuple[str, ...] = (", "ORDER_PORT_VERBS_RENAMED = ("
        ),
        encoding="utf-8",
    )

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "ORDER_PORT_VERBS" in result.detail, result.detail
    assert "DERIVED" in result.detail or "derived" in result.detail.lower(), (
        result.detail
    )


# --------------------------------------------------------------------------
# PLANT (i) — a sleep in a send verb. STRUCTURAL arm only.
# --------------------------------------------------------------------------


def test_a_SLEEP_planted_in_place_order_FAILS_and_NAMES_the_sleep_and_the_verb(
    home: Path,
) -> None:
    _patch(home, ANCHOR_PLACE, f"{ANCHOR_PLACE}\n        time.sleep(0)")

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "sleep" in result.detail, result.detail
    assert "place_order" in result.detail, result.detail
    assert "invariant 5" in result.detail, result.detail
    # The SITE names the file and a line number, not just the file.
    assert f"{gate.ADAPTER_FILE}:" in result.site, result.site
    assert any(part.rsplit(":", 1)[-1].isdigit() for part in result.site.split("; ")), (
        result.site
    )


# --------------------------------------------------------------------------
# PLANT (ii) — a lock acquisition in flatten, the protective path.
# --------------------------------------------------------------------------


def test_a_LOCK_ACQUIRE_planted_in_flatten_FAILS_and_NAMES_the_lock_and_flatten(
    home: Path,
) -> None:
    _add_threading(home)
    _patch(
        home,
        ANCHOR_FLATTEN,
        f"{ANCHOR_FLATTEN}\n"
        "        _planted_lock.acquire()\n"
        "        _planted_lock.release()",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "lock acquisition" in result.detail, result.detail
    assert ".acquire" in result.detail, result.detail
    assert "flatten" in result.detail, result.detail


def test_a_WITH_LOCK_planted_in_disconnect_FAILS_and_NAMES_the_with_and_the_verb(
    home: Path,
) -> None:
    _add_threading(home)
    _patch(
        home,
        ANCHOR_DISCONNECT,
        "        self._connected = False\n"
        "        with _planted_lock:\n"
        "            pass\n"
        "        # Close the gate too:",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "with <already-constructed object>" in result.detail, result.detail
    assert "disconnect" in result.detail, result.detail


# --------------------------------------------------------------------------
# PLANT (iii) — a genuinely SLOW send. TIMED arm only: a busy-wait contains no
# banned construct, so the AST walk is silent about it by construction.
# --------------------------------------------------------------------------


def test_a_SLOW_FLATTEN_FAILS_and_NAMES_the_ELAPSED_TIME_against_the_BUDGET(
    home: Path,
) -> None:
    _patch(
        home,
        ANCHOR_FLATTEN,
        f"{ANCHOR_FLATTEN}\n"
        f"        _planted_deadline = time.monotonic() + {SPIN_S}\n"
        "        while time.monotonic() < _planted_deadline:\n"
        "            pass",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "flatten" in result.detail, result.detail
    assert "IT BLOCKED" in result.detail, result.detail
    assert f"budget of {gate.NONBLOCKING_BUDGET_S}" in result.detail, result.detail
    # The MEASURED elapsed figure is reported, not merely the verdict.
    assert (
        " s, exceeding" in result.detail or "exceeding the budget" in result.detail
    ), result.detail
    assert f"{gate.ADAPTER_FILE}:flatten" in result.site, result.site


def test_the_SLOW_PLANT_is_INVISIBLE_to_the_structural_arm(home: Path) -> None:
    """Proof the two arms are independent: only the TIMED arm names the spin."""
    _patch(
        home,
        ANCHOR_FLATTEN,
        f"{ANCHOR_FLATTEN}\n"
        f"        _planted_deadline = time.monotonic() + {SPIN_S}\n"
        "        while time.monotonic() < _planted_deadline:\n"
        "            pass",
    )
    walk = gate._arm_structural(home)  # pylint: disable=protected-access

    assert walk.blocked == "", walk
    assert walk.findings == [], walk.findings


# --------------------------------------------------------------------------
# PLANT (iv) — the D1.22 honest limit deleted.
# --------------------------------------------------------------------------


def test_DELETING_the_D1_22_CAVEAT_FAILS_and_NAMES_the_missing_statement(
    home: Path,
) -> None:
    _patch(home, ANCHOR_CAVEAT, "SOME bytes")

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "D1.22-caveat" in result.site, result.site
    assert "the-finding" in result.detail, result.detail
    assert "zero bytes delivered to the peer" in result.detail, result.detail
    assert "ABSORBS" in result.detail, result.detail


def test_the_CAVEAT_ARM_survives_REWRAPPING_and_only_fails_on_DELETION(
    home: Path,
) -> None:
    """Whitespace-normalised matching: re-wrapping a paragraph is not deletion."""
    path = _adapter(home)
    text = path.read_text(encoding="utf-8")
    assert "10204 B in asyncio's buffer, and ZERO bytes\n  delivered" in text
    path.write_text(
        text.replace(
            "10204 B in asyncio's buffer, and ZERO bytes\n  delivered",
            "10204 B in asyncio's buffer,\n  and ZERO bytes delivered",
        ),
        encoding="utf-8",
    )

    result = _run(home)

    assert result.status is Status.PASS, result


# --------------------------------------------------------------------------
# CANNOT_MEASURE, never PASS
# --------------------------------------------------------------------------


def test_an_ABSENT_ADAPTER_is_CANNOT_MEASURE_not_PASS(home: Path) -> None:
    _adapter(home).unlink()

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert gate.ADAPTER_FILE in result.detail, result.detail
    assert "absent" in result.detail, result.detail


def test_an_EMPTY_ADAPTER_is_CANNOT_MEASURE_not_PASS(home: Path) -> None:
    """An empty walk is the classic green-on-nothing (§7.12 hole 2)."""
    _adapter(home).write_text("", encoding="utf-8")

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "not an order adapter" in result.detail, result.detail


def test_an_UNPARSEABLE_ADAPTER_is_CANNOT_MEASURE_not_PASS(home: Path) -> None:
    _adapter(home).write_text("def broken(:\n", encoding="utf-8")

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "could not be parsed" in result.detail, result.detail


def test_a_STUB_carrying_ONE_verb_name_is_CANNOT_MEASURE_not_PASS(home: Path) -> None:
    """§7.12 hole 4 — a name-alike is not the subject."""
    _adapter(home).write_text(
        "class NotReallyTheAdapter:\n    def flatten(self):\n        return None\n",
        encoding="utf-8",
    )

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert str(gate.PORT_QUORUM) in result.detail, result.detail
    assert "not an order adapter" in result.detail, result.detail


def test_an_ABSENT_CONFIG_leaves_the_TIMED_arm_CANNOT_MEASURE_not_PASS(
    home: Path,
) -> None:
    """The structural arm alone must never certify (check contract rule 10)."""
    (home / gate.CONFIG_FILE).unlink()

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert gate.CONFIG_FILE in result.detail, result.detail
    assert "BEHAVIOURAL arm could not run" in result.detail, result.detail


# --------------------------------------------------------------------------
# THE THIRD STEP — plants removed, the same tree passing again
# --------------------------------------------------------------------------


def test_a_PLANT_APPLIED_AND_REVERTED_leaves_the_gate_GREEN_on_the_same_tree(
    home: Path,
) -> None:
    before = _adapter(home).read_bytes()
    _patch(home, ANCHOR_PLACE, f"{ANCHOR_PLACE}\n        time.sleep(0)")

    planted = _run(home)
    _adapter(home).write_bytes(before)
    restored = _run(home)

    assert planted.status is Status.FAIL_NEEDS_OPERATOR, planted
    assert restored.status is Status.PASS, restored
    assert _adapter(home).read_bytes() == before, "the control was not restored"


# --------------------------------------------------------------------------
# THE GATE ITSELF LEAVES NOTHING BEHIND
# --------------------------------------------------------------------------


def test_the_GATE_LEAVES_THE_INTERPRETER_AS_IT_FOUND_IT(home: Path) -> None:
    real = {name: sys.modules.get(name) for name in gate.PURGE_MODULES}
    paths_before = list(sys.path)

    _run(home)

    assert sys.path == paths_before, "the gate leaked a sys.path entry"
    for name, module in real.items():
        assert sys.modules.get(name) is module, (
            f"the gate left the tmp_path copy of {name} in sys.modules"
        )


def test_the_GATE_RESTORES_the_adapter_logger(home: Path) -> None:
    import logging  # pylint: disable=import-outside-toplevel

    log = logging.getLogger("nix.broker_order.ibkr")
    level_before, propagate_before = log.level, log.propagate

    _run(home)

    assert log.level == level_before, "the gate left the adapter logger silenced"
    assert log.propagate == propagate_before, "the gate left propagation off"


def test_the_PRODUCTION_TREE_is_byte_identical_afterwards(home: Path) -> None:
    """Doctrine C.8 — no plant may reach a production artifact."""
    before = {
        rel: hashlib.sha256((REPO / rel).read_bytes()).hexdigest()
        for rel in PRODUCTION_FILES
    }

    _patch(home, ANCHOR_PLACE, f"{ANCHOR_PLACE}\n        time.sleep(0)")
    _run(home)
    _run(REPO)

    after = {
        rel: hashlib.sha256((REPO / rel).read_bytes()).hexdigest()
        for rel in PRODUCTION_FILES
    }
    assert after == before, "a production artifact was modified by this suite"
