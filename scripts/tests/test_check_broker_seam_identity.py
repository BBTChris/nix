"""The can-fail suite for `checks/check_broker_seam_identity.py` (Module 2, B1).

Structure follows `nix_check_contract.md` §5.1: **non-vacuity FIRST** (the gate
is green on the real tree), then one planted defect PER ARM — each of which must
turn the gate red (or light blue) **and NAME the specific verb, member or
signature**, never merely move the exit code (check-contract rule 11) — then the
plants removed and the same tree passing again.

**NO PLANT TOUCHES A PRODUCTION FILE** (doctrine C.8). Every control builds a
throwaway `nix_home` under `tmp_path` holding COPIES of the three seam modules,
and a plant is an APPEND to a copy. `scripts/broker/*.py` is read and never
written by this suite — `test_the_REAL_SEAM_SOURCES_are_byte_identical_after`
re-hashes them at the end to prove it.
"""

# pylint: disable=missing-function-docstring,missing-module-docstring
# pylint: disable=use-implicit-booleaness-not-comparison
# missing-function-docstring: every test's NAME is its assertion, which is the
# convention this suite tree uses throughout. use-implicit-booleaness-not-
# comparison: `gate.DEPENDS_ON == ()` is asserting the declaration is EXACTLY
# the empty tuple, not merely falsey — `not gate.DEPENDS_ON` would also accept
# None, [] or "", and the declaration's TYPE is part of what verify.py reads.
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

import check_broker_seam_identity as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)

FILES = (
    "scripts/broker/broker_seam.py",
    "scripts/broker/broker_order_config.py",
    "scripts/broker/broker_order_ibkr.py",
)

#: Hashed BEFORE any test runs, compared AFTER — the freeze, measured.
_BEFORE = {rel: hashlib.sha256((REPO / rel).read_bytes()).hexdigest() for rel in FILES}


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """A throwaway `nix_home` holding COPIES of the seam modules."""
    (tmp_path / "scripts" / "broker").mkdir(parents=True)
    for rel in FILES:
        shutil.copy(REPO / rel, tmp_path / rel)
    return tmp_path


def _run(nix_home: Path):
    return gate.run(Mode.VERIFY, Context(nix_home=nix_home, mode=Mode.VERIFY))


def _append(home: Path, rel: str, source: str) -> None:
    with (home / rel).open("a", encoding="utf-8") as handle:
        handle.write("\n\n" + source.strip() + "\n")


SEAM = "scripts/broker/broker_seam.py"
ADAPTER = "scripts/broker/broker_order_ibkr.py"


# --------------------------------------------------------------------------
# NON-VACUITY FIRST — the gate is GREEN on the real tree
# --------------------------------------------------------------------------


def test_the_REAL_TREE_passes() -> None:
    result = _run(REPO)

    assert result.status is Status.PASS, result
    assert "ORDER_PORT_VERBS=9" in result.evidence, result.evidence
    assert "ORDER_EVENTS=7" in result.evidence, result.evidence


def test_the_COPIED_TREE_passes_so_a_PLANT_is_the_only_variable(home: Path) -> None:
    result = _run(home)

    assert result.status is Status.PASS, result


def test_the_GATE_DECLARES_ITS_SUBJECTS_and_refuses_to_correct() -> None:
    assert SEAM in gate.SUBJECTS, gate.SUBJECTS
    assert ADAPTER in gate.SUBJECTS, gate.SUBJECTS
    assert gate.CORRECTABLE is False
    assert gate.NON_CORRECTABLE_REASON
    assert gate.DEPENDS_ON == ()


def test_the_MEMBER_SET_is_DERIVED_not_a_LITERAL_in_this_gate() -> None:
    """§7.12 answer 3: no hardcoded roster lives in the check's source."""
    source = Path(gate.__file__).read_text(encoding="utf-8")
    body = source.split('"""', 2)[2]  # everything after the module docstring
    for verb in ("place_order", "query_order_status", "on_fill", "on_margin"):
        assert verb not in body, (
            f"{verb!r} is spelled out in the gate's code — the expected set must "
            "be derived by introspection, not typed here"
        )


# --------------------------------------------------------------------------
# PLANT 1 (ARM 2/ARM 3) — a roster verb the Protocol and adapter lack
# --------------------------------------------------------------------------


def test_a_MISSING_VERB_fails_and_NAMES_the_verb(home: Path) -> None:
    _append(home, SEAM, 'ORDER_PORT_VERBS = ORDER_PORT_VERBS + ("ghost_verb",)')

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "ghost_verb" in result.detail, result.detail
    assert "MISSING verb 'ghost_verb'" in result.detail, result.detail
    assert "IBKRBrokerOrder does not implement it" in result.detail, result.detail


# --------------------------------------------------------------------------
# PLANT 2 (ARM 2, the SUPERSET arm — the hole nothing else on the tree closes)
# --------------------------------------------------------------------------


def test_an_EXTRA_PROTOCOL_MEMBER_fails_and_NAMES_the_member(home: Path) -> None:
    _append(
        home,
        SEAM,
        "def _planted_extra(self) -> None: ...\n"
        "BrokerOrderPort.planted_extra = _planted_extra",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "EXTRA verb 'planted_extra'" in result.detail, result.detail
    assert "STRICT SUPERSET" in result.detail, result.detail


def test_an_EXTRA_SINK_MEMBER_fails_and_NAMES_the_event(home: Path) -> None:
    _append(
        home,
        SEAM,
        "def _planted_event(self) -> None: ...\n"
        "OrderEventSink.on_planted = _planted_event",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "EXTRA event 'on_planted'" in result.detail, result.detail
    assert "ORDER_EVENTS does not name it" in result.detail, result.detail


# --------------------------------------------------------------------------
# PLANT 3 (ARM 4) — a verb whose parameter shape diverges from the Protocol
# --------------------------------------------------------------------------


def test_a_WRONG_ARITY_VERB_fails_and_NAMES_BOTH_SIGNATURES(home: Path) -> None:
    _append(
        home,
        ADAPTER,
        "def _planted_arity(self, client_order_id, extra_param) -> None: ...\n"
        "IBKRBrokerOrder.cancel_order = _planted_arity",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "SIGNATURE MISMATCH on verb 'cancel_order'" in result.detail, result.detail
    # BOTH sides named, not just "they differ".
    assert "cancel_order(self, client_order_id: 'ClientOrderId')" in result.detail, (
        result.detail
    )
    assert "cancel_order(self, client_order_id, extra_param)" in result.detail, (
        result.detail
    )


def test_a_RENAMED_PARAMETER_fails_even_though_the_ARITY_MATCHES(home: Path) -> None:
    """Shape is (name, kind, has_default) — a rename is a caller-visible break."""
    _append(
        home,
        ADAPTER,
        "def _planted_rename(self, coid) -> None: ...\n"
        "IBKRBrokerOrder.cancel_order = _planted_rename",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "SIGNATURE MISMATCH on verb 'cancel_order'" in result.detail, result.detail
    assert "coid" in result.detail, result.detail


def test_a_DROPPED_DEFAULT_fails_and_NAMES_flatten(home: Path) -> None:
    """`flatten(symbol=None)` losing its default changes every call site."""
    _append(
        home,
        ADAPTER,
        "def _planted_default(self, symbol) -> None: ...\n"
        "IBKRBrokerOrder.flatten = _planted_default",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "SIGNATURE MISMATCH on verb 'flatten'" in result.detail, result.detail


# --------------------------------------------------------------------------
# PLANT 4 (ARM 1) — an EMPTY roster must NEVER be a PASS
# --------------------------------------------------------------------------


def test_an_EMPTY_VERB_ROSTER_is_NOT_A_PASS_and_says_VACUOUS(home: Path) -> None:
    _append(home, SEAM, "ORDER_PORT_VERBS = ()")

    result = _run(home)

    assert result.status is not Status.PASS, result
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "VACUOUS" in result.detail, result.detail
    assert "ORDER_PORT_VERBS" in result.detail, result.detail


def test_an_EMPTY_EVENT_ROSTER_is_NOT_A_PASS_and_says_VACUOUS(home: Path) -> None:
    _append(home, SEAM, "ORDER_EVENTS = ()")

    result = _run(home)

    assert result.status is not Status.PASS, result
    assert "VACUOUS" in result.detail, result.detail
    assert "ORDER_EVENTS" in result.detail, result.detail


# --------------------------------------------------------------------------
# PLANT 5 (ARM 5) — an UNINSPECTABLE verb is CANNOT_MEASURE, never a PASS
# --------------------------------------------------------------------------


def test_an_UNINSPECTABLE_VERB_is_CANNOT_MEASURE_and_NAMES_it(home: Path) -> None:
    _append(
        home,
        SEAM,
        "class _Opaque:\n"
        "    @property\n"
        "    def __signature__(self):\n"
        "        raise ValueError('planted: C-implemented, no signature')\n"
        "    def __call__(self, *a, **k): ...\n"
        "BrokerOrderPort.get_margin = _Opaque()",
    )

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "get_margin" in result.detail, result.detail
    assert "UNINSPECTABLE" in result.detail, result.detail
    assert "ValueError" in result.detail, result.detail


# --------------------------------------------------------------------------
# PLANT 6 (ARM 1) — a STUB standing in for the real adapter
# --------------------------------------------------------------------------


def test_a_STUB_STANDING_IN_FOR_THE_ADAPTER_is_CANNOT_MEASURE(home: Path) -> None:
    _append(
        home,
        ADAPTER,
        "from broker_seam import StubBrokerOrder as _Stand_in\n"
        "IBKRBrokerOrder = _Stand_in",
    )

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "StubBrokerOrder" in result.detail, result.detail
    assert "NOT the real" in result.detail, result.detail


# --------------------------------------------------------------------------
# THE THIRD STEP — the plants removed, the same tree passing again
# --------------------------------------------------------------------------


def test_a_PLANT_APPLIED_AND_REVERTED_leaves_the_gate_GREEN_on_the_same_tree(
    home: Path,
) -> None:
    before = (home / SEAM).read_bytes()
    _append(home, SEAM, 'ORDER_PORT_VERBS = ORDER_PORT_VERBS + ("ghost_verb",)')

    planted = _run(home)
    (home / SEAM).write_bytes(before)
    restored = _run(home)

    assert planted.status is Status.FAIL_NEEDS_OPERATOR, planted
    assert restored.status is Status.PASS, restored
    assert (home / SEAM).read_bytes() == before, "the control was not restored"


def test_EVERY_ADAPTER_PLANT_REVERTS_to_GREEN(home: Path) -> None:
    before = (home / ADAPTER).read_bytes()
    _append(
        home,
        ADAPTER,
        "def _planted_arity(self, client_order_id, extra_param) -> None: ...\n"
        "IBKRBrokerOrder.cancel_order = _planted_arity",
    )

    planted = _run(home)
    (home / ADAPTER).write_bytes(before)
    restored = _run(home)

    assert planted.status is Status.FAIL_NEEDS_OPERATOR, planted
    assert restored.status is Status.PASS, restored


# --------------------------------------------------------------------------
# CANNOT_MEASURE, never PASS — and the interpreter left as found
# --------------------------------------------------------------------------


def test_an_ABSENT_SEAM_is_CANNOT_MEASURE(home: Path) -> None:
    (home / SEAM).unlink()

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "absent" in result.detail, result.detail


def test_an_UNIMPORTABLE_SEAM_is_CANNOT_MEASURE_naming_the_exception(
    home: Path,
) -> None:
    _append(home, SEAM, "raise RuntimeError('planted: the seam will not import')")

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "RuntimeError" in result.detail, result.detail
    assert "never a PASS" in result.detail, result.detail


def test_the_GATE_LEAVES_THE_INTERPRETER_AS_IT_FOUND_IT(home: Path) -> None:
    real = {name: sys.modules.get(name) for name in gate.MODULES}
    paths_before = list(sys.path)

    _run(home)

    assert sys.path == paths_before, "the gate leaked a sys.path entry"
    for name, module in real.items():
        assert sys.modules.get(name) is module, (
            f"the gate left the tmp_path copy of {name} in sys.modules"
        )


# --------------------------------------------------------------------------
# THE FREEZE, MEASURED
# --------------------------------------------------------------------------


def test_the_REAL_SEAM_SOURCES_are_byte_identical_after_the_suite() -> None:
    after = {
        rel: hashlib.sha256((REPO / rel).read_bytes()).hexdigest() for rel in FILES
    }

    assert after == _BEFORE, "a plant reached a production file (doctrine C.8)"
