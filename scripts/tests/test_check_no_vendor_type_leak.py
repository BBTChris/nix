"""ARC 059 — the can-fail suite for `checks/check_no_vendor_type_leak.py`.

Structure follows `nix_check_contract.md` §5.1, "plant BOTH": non-vacuity
FIRST (the gate PASSES on the real tree and says what it measured), then one
plant per ARM — each of which must make the gate FAIL **and NAME the leaked
type, the offending import, or the verb** (check contract rule 11: assert the
REASON in the message, never the exit code and never merely `status != PASS`) —
then the plant removed and the same tree passing again.

**NO PLANT TOUCHES A PRODUCTION FILE** (doctrine C.8). Every control builds a
throwaway `nix_home` under `tmp_path` holding COPIES of the two subjects, and
`test_the_REAL_SUBJECTS_are_BYTE_IDENTICAL_after_the_suite` re-reads the real
`scripts/broker/*.py` and compares them against the bytes read at import time.

The arms, and the plant that proves each one can fire:

  ARM 1  vacuity guard        -> the roster constant renamed, and an absent
                                 subject: CANNOT_MEASURE, never PASS
  ARM 2  seam imports         -> `import ib_async` injected into the seam COPY
  ARM 3  §2A annotations      -> a port verb returning `ib_async.Trade`, and an
                                 event carrying `Execution`
  ARM 4  adapter returns/emits-> `return trade` from `query_order_status`, and
                                 `on_cancel` emitted with `trade.orderStatus`
  ARM 5  declared exception   -> the `on_ack.reason` justification ANCHOR
                                 deleted, and the allowance's annotation widened
"""

# pylint: disable=missing-function-docstring,missing-module-docstring
# pylint: disable=use-implicit-booleaness-not-comparison
# Same rulings as test_check_broker_seam_identity.py: a test's name is its
# assertion, and an exact-tuple comparison on a DECLARATION is deliberate.
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.append(str(REPO / "checks"))

import check_no_vendor_type_leak as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)

SEAM = gate.SEAM
ADAPTER = gate.ADAPTER
FILES = (SEAM, ADAPTER)

#: Read ONCE at import, compared again at the end of the suite. The freeze is
#: measured, not asserted in prose.
REAL_BYTES = {rel: (REPO / rel).read_bytes() for rel in FILES}


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """A throwaway nix_home holding COPIES of the two subjects."""
    (tmp_path / "scripts" / "broker").mkdir(parents=True)
    for rel in FILES:
        shutil.copy(REPO / rel, tmp_path / rel)
    return tmp_path


def _run(nix_home: Path):
    return gate.run(Mode.VERIFY, Context(nix_home=nix_home, mode=Mode.VERIFY))


def _plant(home: Path, rel: str, old: str, new: str, *, count: int = 0) -> None:
    """Rewrite a COPY. Asserts the anchor was found, so a stale plant is loud."""
    path = home / rel
    text = path.read_text(encoding="utf-8")
    assert old in text, f"plant anchor not found in {rel}: {old!r}"
    path.write_text(
        text.replace(old, new) if count == 0 else text.replace(old, new, count),
        encoding="utf-8",
    )


# --------------------------------------------------------------------------
# NON-VACUITY FIRST
# --------------------------------------------------------------------------


def test_the_REAL_TREE_passes() -> None:
    result = _run(REPO)

    assert result.status is Status.PASS, result
    assert "invariant 2" in result.evidence, result.evidence


def test_the_REAL_TREE_evidence_reports_a_NON_ZERO_POPULATION() -> None:
    """§7.12 answer 2: a collapse to an empty walk must be visible in the PASS."""
    result = _run(REPO)

    assert result.status is Status.PASS, result
    assert "ORDER_PORT_VERBS=9 verbs" in result.evidence, result.evidence
    assert "ORDER_EVENTS=7 events" in result.evidence, result.evidence
    assert "9 adapter roster methods walked" in result.evidence, result.evidence
    for zero in ("locating 0 ", " 0 adapter roster methods", "0 event emissions"):
        assert zero not in result.evidence, result.evidence


def test_the_COPIED_TREE_passes_before_any_plant(home: Path) -> None:
    """The control the plants are measured against."""
    assert _run(home).status is Status.PASS, _run(home)


def test_the_GATE_DECLARES_BOTH_SUBJECTS_and_REFUSES_TO_CORRECT() -> None:
    assert SEAM in gate.SUBJECTS, gate.SUBJECTS
    assert ADAPTER in gate.SUBJECTS, gate.SUBJECTS
    assert gate.CORRECTABLE is False
    assert gate.NON_CORRECTABLE_REASON.strip()
    assert gate.DEPENDS_ON == ()


def test_the_GATE_HARDCODES_NO_ABSOLUTE_HOME_PATH() -> None:
    """§7.12 answer 9: a hardcoded home would measure the real tree forever."""
    source = (REPO / "checks" / "check_no_vendor_type_leak.py").read_text(
        encoding="utf-8"
    )
    assert "/home/" not in source


# --------------------------------------------------------------------------
# ARM 2 — a vendor import in the seam
# --------------------------------------------------------------------------


def test_a_VENDOR_IMPORT_IN_THE_SEAM_fails_and_NAMES_the_module(home: Path) -> None:
    (home / SEAM).write_text(
        (home / SEAM).read_text(encoding="utf-8") + "\nimport ib_async\n",
        encoding="utf-8",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "ib_async" in result.detail, result.detail
    assert "the SEAM imports the vendor SDK" in result.detail, result.detail


def test_a_FROM_VENDOR_IMPORT_IN_THE_SEAM_fails_and_NAMES_the_TYPE(
    home: Path,
) -> None:
    (home / SEAM).write_text(
        (home / SEAM).read_text(encoding="utf-8") + "\nfrom ib_async import Trade\n",
        encoding="utf-8",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "'Trade'" in result.detail, result.detail
    assert "ib_async" in result.detail, result.detail


# --------------------------------------------------------------------------
# ARM 3 — a vendor type on the §2A surface
# --------------------------------------------------------------------------


def test_a_VENDOR_RETURN_ON_A_PORT_VERB_fails_and_NAMES_the_VERB_and_TYPE(
    home: Path,
) -> None:
    _plant(
        home,
        SEAM,
        "def query_order_status(self, client_order_id: ClientOrderId) -> OrderStatus:",
        "def query_order_status(self, client_order_id: ClientOrderId) -> ib_async.Trade:",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "query_order_status" in result.detail, result.detail
    assert "ib_async.Trade" in result.detail, result.detail
    assert "RETURNS the vendor type" in result.detail, result.detail


def test_a_VENDOR_TYPE_ON_AN_EVENT_fails_and_NAMES_the_EVENT_and_TYPE(
    home: Path,
) -> None:
    _plant(
        home,
        SEAM,
        "def on_cancel(self, client_order_id: ClientOrderId, done_qty: int) -> None:",
        "def on_cancel(self, client_order_id: ClientOrderId, done_qty: Execution) -> None:",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "on_cancel" in result.detail, result.detail
    assert "'Execution'" in result.detail, result.detail
    assert "CARRIES the vendor type" in result.detail, result.detail


# --------------------------------------------------------------------------
# ARM 4 — the adapter returning / emitting a vendor object
# --------------------------------------------------------------------------


def test_a_VENDOR_OBJECT_RETURNED_BY_A_PORT_VERB_fails_and_NAMES_the_VERB(
    home: Path,
) -> None:
    _plant(
        home,
        ADAPTER,
        "        st = trade.orderStatus\n",
        "        return trade\n        st = trade.orderStatus\n",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "query_order_status" in result.detail, result.detail
    assert "return trade" in result.detail, result.detail
    assert "RETURNS a vendor-derived value" in result.detail, result.detail


def test_a_VENDOR_OBJECT_ON_AN_EMITTED_EVENT_fails_and_NAMES_the_EVENT(
    home: Path,
) -> None:
    _plant(
        home,
        ADAPTER,
        "self._sink.on_cancel(cid, int(trade.orderStatus.filled))",
        "self._sink.on_cancel(cid, trade.orderStatus)",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "'on_cancel'" in result.detail, result.detail
    assert "trade.orderStatus" in result.detail, result.detail
    assert "is EMITTED carrying a vendor-derived value" in result.detail, result.detail


def test_an_UNDECIDABLE_RETURN_is_CANNOT_MEASURE_and_NAMES_IT(home: Path) -> None:
    """§7.12 answer 5 — the honesty clause, proven able to fire.

    A gate that quietly assumed an unresolvable expression was clean would be
    worse than one that says it cannot tell. `self._not_a_real_helper()`
    resolves to no method, no attribute and no annotation, so the classifier
    returns UNDECIDED — and the verdict must be CANNOT_MEASURE naming the
    method and the exact expression, never PASS.
    """
    _plant(
        home,
        ADAPTER,
        "        st = trade.orderStatus\n",
        "        return self._not_a_real_helper()\n        st = trade.orderStatus\n",
    )

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "query_order_status" in result.detail, result.detail
    assert "self._not_a_real_helper()" in result.detail, result.detail
    assert "NEVER assumed clean" in result.detail, result.detail


def test_an_UNDECIDABLE_EMISSION_ARGUMENT_is_CANNOT_MEASURE_and_NAMES_IT(
    home: Path,
) -> None:
    _plant(
        home,
        ADAPTER,
        "self._sink.on_cancel(cid, int(trade.orderStatus.filled))",
        "self._sink.on_cancel(cid, self._not_a_real_helper())",
    )

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "emits on_cancel" in result.detail, result.detail
    assert "self._not_a_real_helper()" in result.detail, result.detail


def test_the_INT_COERCION_IS_WHAT_KEEPS_THE_EMISSION_CLEAN(home: Path) -> None:
    """The control for the plant above — the classifier discriminates.

    `on_cancel(cid, int(trade.orderStatus.filled))` is CLEAN and
    `on_cancel(cid, trade.orderStatus)` is a leak. A classifier that reddened
    both, or neither, would be indistinguishable from one that reads nothing;
    the difference between them is exactly the mapping invariant 2 asks for.
    """
    before = _run(home)
    _plant(
        home,
        ADAPTER,
        "self._sink.on_cancel(cid, int(trade.orderStatus.filled))",
        "self._sink.on_cancel(cid, str(trade.orderStatus.filled))",
    )

    after = _run(home)

    assert before.status is Status.PASS, before
    assert after.status is Status.PASS, after


# --------------------------------------------------------------------------
# ARM 5 — the declared on_ack.reason exception, held to its justification
# --------------------------------------------------------------------------


def test_the_ONLY_DECLARED_EXCEPTION_is_on_ack_reason() -> None:
    """It is ONE allowance, hardcoded, cited — never a growable list."""
    assert len(gate.DECLARED_EXCEPTIONS) == 1, gate.DECLARED_EXCEPTIONS
    allowance = gate.DECLARED_EXCEPTIONS[0]
    assert allowance.site == "OrderEventSink.on_ack"
    assert allowance.field_name == "reason"
    assert "1528-1530" in allowance.citation, allowance.citation


def test_the_JUSTIFICATION_ANCHOR_REMOVED_fails_and_NAMES_the_ANCHOR(
    home: Path,
) -> None:
    _plant(home, SEAM, "deliberately NOT vendor-neutral", "just descriptive")

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "JUSTIFICATION ANCHOR" in result.detail, result.detail
    assert "deliberately NOT vendor-neutral" in result.detail, result.detail
    assert "on_ack" in result.detail, result.detail
    assert "may not outlive the justification" in result.detail, result.detail


def test_WIDENING_THE_ALLOWANCE_ANNOTATION_fails_and_NAMES_THE_WIDENING(
    home: Path,
) -> None:
    """The allowance covers vendor CONTENT in a neutral str, not a vendor TYPE."""
    _plant(
        home,
        SEAM,
        "        reason: str | None = None,\n        *,\n        reject_category",
        "        reason: object | None = None,\n        *,\n        reject_category",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "WIDENING of a ratified exception" in result.detail, result.detail
    assert "'object | None'" in result.detail, result.detail


def test_the_ALLOWANCE_SITE_DELETED_fails_and_NAMES_IT(home: Path) -> None:
    _plant(
        home,
        SEAM,
        "class OrderEventSink(Protocol):",
        "class OrderEventSinkX(Protocol):",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "OrderEventSink.on_ack" in result.detail, result.detail
    assert "no longer declares" in result.detail, result.detail


# --------------------------------------------------------------------------
# ARM 1 — the vacuity guard. CANNOT_MEASURE, never PASS.
# --------------------------------------------------------------------------


def test_an_ABSENT_SEAM_is_CANNOT_MEASURE_not_PASS(home: Path) -> None:
    (home / SEAM).unlink()

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "absent" in result.detail, result.detail
    assert SEAM in result.detail, result.detail


def test_an_ABSENT_ADAPTER_is_CANNOT_MEASURE_not_PASS(home: Path) -> None:
    (home / ADAPTER).unlink()

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert ADAPTER in result.detail, result.detail


def test_an_EMPTY_SEAM_is_CANNOT_MEASURE_not_PASS(home: Path) -> None:
    (home / SEAM).write_text("", encoding="utf-8")

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert gate.VERB_ROSTER in result.detail, result.detail


def test_an_UNPARSEABLE_SEAM_is_CANNOT_MEASURE_not_PASS(home: Path) -> None:
    (home / SEAM).write_text("def (:\n", encoding="utf-8")

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "could not be parsed" in result.detail, result.detail


def test_a_RENAMED_ROSTER_is_CANNOT_MEASURE_not_PASS(home: Path) -> None:
    """§7.12 answer 3: the roster is DERIVED, so losing it is loud, not silent."""
    _plant(
        home,
        SEAM,
        "ORDER_PORT_VERBS: tuple[str, ...] = (",
        "ORDER_PORT_VERBS_RENAMED: tuple[str, ...] = (",
    )

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "ORDER_PORT_VERBS not found" in result.detail, result.detail


def test_an_EMPTIED_ROSTER_is_CANNOT_MEASURE_not_PASS(home: Path) -> None:
    """An empty walk must NEVER be a PASS — the §7.12 hole this gate exists for."""
    text = (home / SEAM).read_text(encoding="utf-8")
    start = text.index("ORDER_PORT_VERBS: tuple[str, ...] = (")
    end = text.index(")", text.index('"get_margin",', start)) + 1
    (home / SEAM).write_text(
        text[:start] + "ORDER_PORT_VERBS: tuple[str, ...] = ()" + text[end:],
        encoding="utf-8",
    )

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "EMPTY roster" in result.detail, result.detail


def test_a_ROSTER_VERB_THE_SEAM_NEVER_DECLARES_fails_and_NAMES_IT(
    home: Path,
) -> None:
    _plant(
        home,
        SEAM,
        '    "get_margin",\n)\n\nORDER_EVENTS',
        '    "get_margin",\n    "settle_everything",\n)\n\nORDER_EVENTS',
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "settle_everything" in result.detail, result.detail
    assert "the seam declares nowhere" in result.detail, result.detail


# --------------------------------------------------------------------------
# THE THIRD STEP — plants removed, the same tree passing again
# --------------------------------------------------------------------------


def test_a_PLANT_APPLIED_AND_REVERTED_leaves_the_gate_GREEN_on_the_same_tree(
    home: Path,
) -> None:
    before = (home / SEAM).read_bytes()
    (home / SEAM).write_text(
        before.decode("utf-8") + "\nimport ib_async\n", encoding="utf-8"
    )

    planted = _run(home)
    (home / SEAM).write_bytes(before)
    restored = _run(home)

    assert planted.status is Status.FAIL_NEEDS_OPERATOR, planted
    assert restored.status is Status.PASS, restored
    assert (home / SEAM).read_bytes() == before, "the control was not restored"


def test_the_ADAPTER_PLANT_APPLIED_AND_REVERTED_leaves_the_gate_GREEN(
    home: Path,
) -> None:
    before = (home / ADAPTER).read_bytes()
    _plant(
        home,
        ADAPTER,
        "        st = trade.orderStatus\n",
        "        return trade\n        st = trade.orderStatus\n",
    )

    planted = _run(home)
    (home / ADAPTER).write_bytes(before)
    restored = _run(home)

    assert planted.status is Status.FAIL_NEEDS_OPERATOR, planted
    assert restored.status is Status.PASS, restored


# --------------------------------------------------------------------------
# THE FREEZE — the real subjects are read and never written
# --------------------------------------------------------------------------


def test_the_REAL_SUBJECTS_are_BYTE_IDENTICAL_after_the_suite() -> None:
    for rel in FILES:
        assert (REPO / rel).read_bytes() == REAL_BYTES[rel], (
            f"{rel} was MUTATED by this suite — doctrine C.8: a plant never "
            "touches a production artifact"
        )
