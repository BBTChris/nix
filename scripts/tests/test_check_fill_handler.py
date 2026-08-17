"""ARC 034 / sub-agent A — the can-fail suite for the fill-handler gate.

Structure follows `nix_check_contract.md` §5.1: non-vacuity FIRST, then one plant
per DECLARED PROPERTY that must FAIL and NAME its site, then the plants removed
and the same population passing. A demonstration missing the last step shows only
that a gate can fail.

**No plant touches a production artifact** (doctrine C.8, CHECK-DEBT D3.189).
Every can-fail builds a throwaway `nix_home` under `tmp_path` holding COPIES of
the fill path and everything the gate imports, perturbs the COPY, and drives the
SHIPPED gate's own bytes against it.

**THE PLANTS THAT MATTER MOST** are the two that would otherwise be invisible:

* `test_RELEASING_AGAINST_THE_REQUESTED_QTY_reddens...` changes ONE keyword
  argument — `report.cumulative_qty` becomes `order.qty` — so the handler asks
  for the remainder of a quantity that always equals the requested one. No cancel
  is ever issued, no reservation is released early, and every other arm stays
  green. That is the silent over-stop §4's partial-fill rule exists to prevent,
  and it is only visible because the population drives filled APART from
  requested.
* `test_a_CONSTANT_PER_CONTRACT_RISK_reddens...` makes §7's exposure unit ignore
  the stop distance entirely. The cap then answers the same for every distance,
  which is a cap that is not pricing anything at all — and D3.150's whole finding
  is that this field had no production source to move it.

**ONE DEFECT IN THE GATE WAS FOUND BY THIS SUITE AND FIXED, recorded because the
finding is the deliverable.** `check_fill_handler.run` originally applied its
non-vacuity floors BEFORE reporting defects. Five of the plants below drive a
tallied figure to zero as a CONSEQUENCE of the defect they plant — a handler that
issues no IOC cancel drives `cancels` to zero — so the gate answered
CANNOT_MEASURE over violations it had measured precisely. The floors now run only
on the path to a PASS.

**Every control asserts the REASON** — a substring of `site` or `detail` naming
WHAT was wrong — never the status alone (check contract v2 §11 / §18).
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# protected-access: the non-vacuity controls read the gate's OWN tally and
# population directly, because a floor asserted against a table restated in
# this file would go stale the moment the gate's population moved — which is
# the anchor doctrine C.4 rejects, one layer over.
# pylint: disable=protected-access
# Test names SHOUT the property; the sys.path bootstrap is identical in every
# check test by requirement.

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
# APPENDED, never inserted at the front — loader.py's failure mode #8 note.
sys.path.append(str(REPO / "checks"))

import check_fill_handler as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)

#: Everything the gate imports or reads, copied into the throwaway tree. The gate
#: CONSTRUCTS the whole shipped fill path, so the entire import closure has to be
#: here — a partial copy would make every red below an ImportError rather than a
#: measurement.
_COPIED = (
    "scripts/nixrisk/__init__.py",
    "scripts/nixrisk/seam.py",
    "scripts/nixrisk/picture.py",
    "scripts/nixrisk/execution.py",
    "scripts/nixrisk/stops.py",
    "scripts/nixrisk/positions.py",
    "scripts/nixrisk/reservations.py",
    "scripts/nixrisk/fill_seam.py",
    "scripts/nixrisk/fills.py",
    "scripts/nixrisk/join.py",
    "scripts/nixalloc/__init__.py",
    "scripts/nixalloc/seam.py",
    "scripts/nixalloc/caps.py",
    "scripts/risk_config.py",
    "scripts/broker/broker_seam.py",
)

#: `risk_config` validates the whole `risks/` set at load, so all of it travels.
_CONFIGS = tuple(
    f"risks/{path.name}" for path in sorted((REPO / "risks").glob("*.json"))
)

#: Plant anchors. Each is exact source text from a shipped module; `_plant`
#: asserts the anchor is present, which is the load-bearing half — a plant whose
#: anchor has drifted mutates nothing, the gate stays green, and the control
#: would report that the gate reddens on a change it never saw.
_RELEASE_CALL = "            filled_qty=report.cumulative_qty,"
_ARM_RECORD = "        if converted:\n            steps.append(FillStep.ARM_STOP)"
_FILLED_FROM_ROW = "        filled = abs(write.row.size)"
_MEMO = "        self._armed[order.client_order_id] = state"
_RETURN_PRIOR = "            return prior, False"
_REFUSE_UNAPPROVED = "        if order is None:\n            raise UnapprovedFill("
_PER_CONTRACT = "    return (float(stop_ticks) + pad) * tick_value * weight"
_SINK_PARAM = "        cumulative_qty: int,"
_HANDLER_PARAM = "    def on_fill(self, report: ExecutionReport) -> FillOutcome:"
_ORDER_WRITE_BLOCK = (
    "        sigma = self._remainder.release_remainder(\n"
    "            order.client_order_id,\n"
    "            filled_qty=report.cumulative_qty,\n"
    "            requested_qty=order.qty,\n"
    "        )\n"
    "        steps.append(FillStep.RELEASE_REMAINDER)\n"
    "\n"
    "        write = self._writer.on_fill(report, sum_reservations=sigma)\n"
    "        steps.append(FillStep.ORIGIN_WRITE)"
)
_WRITE_FIRST_BLOCK = (
    "        write = self._writer.on_fill(report, sum_reservations=None)\n"
    "        steps.append(FillStep.ORIGIN_WRITE)\n"
    "\n"
    "        sigma = self._remainder.release_remainder(\n"
    "            order.client_order_id,\n"
    "            filled_qty=report.cumulative_qty,\n"
    "            requested_qty=order.qty,\n"
    "        )\n"
    "        steps.append(FillStep.RELEASE_REMAINDER)"
)

_FILLS = "scripts/nixrisk/fills.py"
_JOIN = "scripts/nixrisk/join.py"
_CAPS = "scripts/nixalloc/caps.py"
_SEAM = "scripts/nixrisk/fill_seam.py"


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """A throwaway tree carrying COPIES of the fill path and its import closure."""
    for rel in _COPIED + _CONFIGS:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / rel, tmp_path / rel)
    return tmp_path


def _run(nix_home: Path):
    return gate.run(Mode.VERIFY, Context(nix_home=nix_home, mode=Mode.VERIFY))


def _plant(where: Path, rel: str, old: str, new: str) -> None:
    """Perturb the COPY, asserting the anchor really was there.

    The assertion is the load-bearing half: a plant whose anchor has drifted
    silently mutates nothing, the gate stays green, and the control reports that
    the gate reddens on a change it never saw — a suite measuring itself.
    """
    path = where / rel
    source = path.read_text(encoding="utf-8")
    assert old in source, f"the plant anchor {old!r} is not in {rel}"
    path.write_text(source.replace(old, new, 1), encoding="utf-8")


# ==========================================================================
# NON-VACUITY FIRST — the gate reaches a real drive and a real reference side
# ==========================================================================


def test_the_REAL_TREE_passes_and_the_EVIDENCE_names_what_was_MEASURED() -> None:
    """The credibility floor: the figures are in evidence, not a restatement."""
    result = _run(REPO)

    assert result.status is Status.PASS, result
    assert "drove 4 confirmed fill(s)" in result.evidence, result.evidence
    assert "ARM_STOP+RELEASE_REMAINDER+ORIGIN_WRITE" in result.evidence, result.evidence
    assert "2 order(s) filled SHORT with 2 IOC cancel(s)" in result.evidence, (
        result.evidence
    )
    assert "2 same-bucket published row(s)" in result.evidence, result.evidence
    # The UNBOUND sentence is part of the deliverable: a green here must not be
    # readable as "production fills reach the correlation cap".
    assert "UNBOUND" in result.evidence, result.evidence
    # The wiring gap is DERIVED from the broker seam, not typed — 1 of 7 today,
    # and the day the Limiter's event handler grows a verb this figure moves on
    # its own instead of going stale (directive 3).
    assert "LimiterFillSink carries 1 of" in result.evidence, result.evidence
    assert "OrderEventSink's 7 verb(s)" in result.evidence, result.evidence


def test_the_WIRING_GAP_FIGURE_is_DERIVED_from_the_broker_seam_not_typed() -> None:
    """A hand-typed 'one of seven' is a restatement that goes stale (directive 3)."""
    gate_source = Path(gate.__file__).read_text(encoding="utf-8")

    assert "seven verbs" not in gate_source, gate_source[:0]
    assert "tally.sink_verbs = sum(" in gate_source
    assert "tally.seam_verbs = len(roster)" in gate_source


def test_EVERY_DECLARED_FLOOR_IS_STRICTLY_BELOW_TODAYS_FIGURE() -> None:
    """Doctrine C.4: a threshold at today's number is an anchor that moves.

    Read off a REAL run rather than from a table in this file, so the day the
    population shrinks toward a floor this control says so.
    """
    defects, tally, refusal = gate._measure(REPO)

    assert not defects, defects
    assert tally is not None, refusal
    for observed, floor, what in (
        (tally.trades, gate.MIN_TRADES, "trades"),
        (tally.full_sequences, gate.MIN_FULL_SEQUENCES, "full sequences"),
        (tally.partial_orders, gate.MIN_PARTIAL_ORDERS, "short fills"),
        (tally.cancels, gate.MIN_CANCELS, "cancels"),
        (tally.conformance_pairs, gate.MIN_CONFORMANCE_PAIRS, "conformance pairs"),
        (
            len(set(tally.cap_answers)),
            gate.MIN_DISTINCT_CAP_ANSWERS,
            "distinct cap answers",
        ),
    ):
        assert floor > 0, what
        assert floor < observed, f"{what}: floor {floor} is not below {observed}"


def test_the_CAP_ANSWERS_REALLY_MOVE_so_the_cap_is_PRICING_not_returning() -> None:
    """The whole point of D3.150: the number the fill published is CONSUMED."""
    _defects, tally, _refusal = gate._measure(REPO)

    assert tally is not None
    assert len(set(tally.cap_answers)) >= 2, tally.cap_answers
    assert tally.cap_used > 0.0, tally.cap_used
    assert tally.cap_contributors == 2, tally.cap_contributors


def test_the_STEP_ORDER_is_READ_FROM_THE_SEAM_and_is_not_a_constant_here() -> None:
    """If the expectation were hardcoded, reordering the seam could not move it."""
    source = (REPO / gate.HANDLER).read_text(encoding="utf-8")
    del source  # the subject is not what is asserted; the GATE's source is
    gate_source = Path(gate.__file__).read_text(encoding="utf-8")

    assert '"ARM_STOP", "RELEASE_REMAINDER", "ORIGIN_WRITE"' not in gate_source
    assert "sorted(step, key=lambda m: m.value)" in gate_source, (
        "the expected order must be derived from the IMPORTED FillStep enum"
    )


def test_the_GATE_DECLARES_BOTH_NEW_MODULES_so_coverage_is_real() -> None:
    """`check_artifact_gate_coverage` counts SUBJECTS; an undeclared module is uncovered."""
    assert "scripts/nixrisk/fills.py" in gate.SUBJECTS, gate.SUBJECTS
    assert "scripts/nixrisk/join.py" in gate.SUBJECTS, gate.SUBJECTS


# ==========================================================================
# THE ORDER — the safety property, planted from both directions
# ==========================================================================


def test_WRITING_BEFORE_RELEASING_reddens_and_NAMES_the_delay(home: Path) -> None:
    """§4 requires the published snapshot to carry the remainder ALREADY released."""
    _plant(home, _FILLS, _ORDER_WRITE_BLOCK, _WRITE_FIRST_BLOCK)

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "step 3 ran before step 2" in result.detail, result.detail
    assert "the seam's FillStep order is" in result.detail, result.detail


def test_REORDERED_SEAM_VALUES_redden_because_the_EXPECTATION_FOLLOWS_THE_SEAM(
    home: Path,
) -> None:
    """The expected order is the SEAM's, so moving the seam moves the expectation."""
    _plant(home, _SEAM, "    ARM_STOP = 1", "    ARM_STOP = 9")

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "are not increasing" in result.detail, result.detail


# ==========================================================================
# CAUSATION — the fill must ARM, and the row must carry THAT distance
# ==========================================================================


def test_a_HANDLER_THAT_NEVER_ARMS_reddens_and_NAMES_the_refusal(home: Path) -> None:
    """No arm ⇒ the origin writer refuses ⇒ the drive raises, and the gate says so."""
    _plant(
        home,
        _FILLS,
        "        state = self._stops.arm(report.price, order)",
        "        state = None  # planted: the stop is never converted",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "UnstoppedFill" in result.detail, result.detail
    assert "FillHandler.on_fill" in result.site, result.site


def test_a_COLLAPSED_TRADE_ID_reaching_the_ROW_reddens(home: Path) -> None:
    """§0a: a fail-closed branch nothing can reach is a branch nothing tests.

    Three plants, because the production join defends itself twice — the mint
    refuses to return its input and the factory probes the policy. Both are
    disabled here so the collapse actually reaches a published row, which is the
    only way `causation_defects`' key comparison is ever driven.
    """
    _plant(home, _JOIN, "_PROBE_ORDERS = 2", "_PROBE_ORDERS = 0")
    _plant(
        home,
        _JOIN,
        "        if trade_id == order.client_order_id:",
        "        if trade_id is None:",
    )
    _plant(
        home,
        _JOIN,
        "        trade_id = (\n"
        '            f"{self._prefix}-{next(self._seq):0{_SEQ_WIDTH}d}'
        '-{order.strategy_id}"\n'
        "        )",
        "        next(self._seq)\n        trade_id = order.client_order_id",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "which IS the client_order_id" in result.detail, result.detail
    assert "D3.177" in result.detail, result.detail


# ==========================================================================
# §4's PARTIAL FILL — the silent over-stop, and the size that is published
# ==========================================================================


def test_RELEASING_AGAINST_THE_REQUESTED_QTY_reddens_and_NAMES_the_missing_cancel(
    home: Path,
) -> None:
    """ONE keyword argument. No cancel is ever issued and the capital stays taken.

    This is the §4 defect that is invisible when `filled == requested`: the
    handler asks for the remainder of a quantity that is the requested one by
    construction, so `requested - filled` is always zero.
    """
    _plant(home, _FILLS, _RELEASE_CALL, "            filled_qty=order.qty,")

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "NO IOC cancel was issued" in result.detail, result.detail
    assert "IocRemainder.release_remainder" in result.site, result.site


def test_CANCELLING_A_FULLY_FILLED_ORDER_reddens_and_says_WHY_THE_COUNT_MATTERS(
    home: Path,
) -> None:
    """The other side of the same arm, which the plant above cannot reach.

    §0a: `_cancel_defects` has two branches and the missing-cancel plant drives
    only one. An unconditional cancel is harmless at the venue and a lie in the
    record — the count of cancels stops being the count of partial fills.
    """
    _plant(
        home,
        _FILLS,
        "        if filled_qty == requested_qty:\n            return False",
        "        if False:  # planted: cancel whether or not a remainder exists\n"
        "            return False",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "IOC cancel(s) were issued anyway" in result.detail, result.detail


def test_A_POSITION_RE_DERIVED_FROM_THE_LAST_INCREMENT_reddens(home: Path) -> None:
    """Doctrine C.9: §4's ledger owns cumulative position, and it is ASKED.

    A writer that used this exec's own increment instead of the ledger's derived
    cumulative is indistinguishable from a correct one on every SINGLE-fill order
    — which is why the late partial fill of `CO-1` is in the population at all.
    """
    _plant(
        home,
        "scripts/nixrisk/positions.py",
        "        filled = self._ledger.order_cumulative(report.order_id)",
        "        filled = report.filled_qty  # planted: the LAST increment",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "must update the row it already wrote" in result.detail, result.detail
    assert "[CO-1/late]" in result.site, result.site


def test_PUBLISHING_THE_REQUESTED_SIZE_reddens_and_NAMES_BOTH_NUMBERS(
    home: Path,
) -> None:
    """§4: 'Limiter sets position = actual filled qty'. Not the size it asked for."""
    _plant(
        home,
        _FILLS,
        _FILLED_FROM_ROW,
        "        filled = order.qty  # planted: the size it ASKED for",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "the ACTUAL filled quantity" in result.detail, result.detail
    assert "silently over-states every partially-filled position" in result.detail


# ==========================================================================
# CONVERTED ONCE — §4's single conversion at the confirmed fill
# ==========================================================================


def test_RECORDING_ARM_STOP_ON_A_STEP_THAT_DID_NOT_RUN_reddens(home: Path) -> None:
    """`FillOutcome.steps` must describe what RAN, never the function's source."""
    _plant(
        home,
        _FILLS,
        _ARM_RECORD,
        "        if True:  # planted: recorded whether or not it converted\n"
        "            steps.append(FillStep.ARM_STOP)",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "a successive partial fill recorded ARM_STOP" in result.detail, result.detail


def test_A_SECOND_CONVERSION_reddens_and_NAMES_the_duplicate(home: Path) -> None:
    """A handler that forgets what it armed re-converts, and the book refuses."""
    _plant(home, _FILLS, _MEMO, "        pass  # planted: nothing is remembered")

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "DuplicateStop" in result.detail, result.detail


def test_A_SUBSTITUTED_STOPSTATE_reddens_though_EVERY_FIELD_MATCHES(
    home: Path,
) -> None:
    """An equal-but-different StopState is not the stop this trade's fill armed."""
    _plant(
        home,
        _FILLS,
        _RETURN_PRIOR,
        "            return dataclasses.replace(prior), False",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "a DIFFERENT StopState object" in result.detail, result.detail


# ==========================================================================
# THE CAP — §7:501 must CONSUME the published distance
# ==========================================================================


def test_a_MIS_SCALED_EXPOSURE_UNIT_reddens_against_THIS_GATES_OWN_ARITHMETIC(
    home: Path,
) -> None:
    """The expected side is §7:501 typed HERE, so the two are two pieces of work."""
    _plant(
        home,
        _CAPS,
        _PER_CONTRACT,
        "    return (float(stop_ticks) + pad) * tick_value * weight * 2.0",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "the distance the fill armed is not the distance the cap is consuming" in (
        result.detail
    ), result.detail


def test_a_CONSTANT_PER_CONTRACT_RISK_reddens_as_A_CAP_THAT_IS_NOT_PRICING(
    home: Path,
) -> None:
    """A cap that answers the same for every distance is not pricing anything.

    The distance is dropped from §7:501's exposure unit entirely, so all three
    drives price identically. Note the verdict: FAIL, not CANNOT_MEASURE. The
    gate reports defects BEFORE its non-vacuity floors precisely so a defect that
    also flattens a tallied figure is reported as the violation it is — see the
    comment in `check_fill_handler.run`, which this control is the measurement
    behind.
    """
    _plant(
        home,
        _CAPS,
        _PER_CONTRACT,
        "    return (99.0 + pad) * tick_value * weight",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "an answer that does not move" in result.detail, result.detail
    assert "nixalloc.caps.admit" in result.site, result.site


# ==========================================================================
# THE SURFACES — the ports, and the §2A event shape the sink must carry
# ==========================================================================


def test_a_DRIFTED_HANDLER_PARAMETER_reddens_though_ISINSTANCE_STILL_PASSES(
    home: Path,
) -> None:
    """`runtime_checkable` isinstance compares METHOD NAMES ONLY. This is the rest."""
    _plant(
        home,
        _FILLS,
        _HANDLER_PARAM,
        "    def on_fill(self, execution_report: ExecutionReport) -> FillOutcome:",
    )
    _plant(
        home,
        _FILLS,
        "        order = self._approved(report)",
        "        report = execution_report\n        order = self._approved(report)",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "do not open with the port's" in result.detail, result.detail
    assert "FillHandler->FillHandlerPort.on_fill" in result.site, result.site


def test_a_SINK_THAT_DRIFTS_FROM_THE_2A_EVENT_reddens_and_NAMES_THE_BROKER_SEAM(
    home: Path,
) -> None:
    """The reference side is `broker_seam.py`, a file the subject cannot edit."""
    _plant(home, _FILLS, _SINK_PARAM, "        running_total: int,")
    _plant(
        home,
        _FILLS,
        "                cumulative_qty=cumulative_qty,",
        "                cumulative_qty=running_total,",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "broker_seam.py" in result.detail, result.detail
    assert "running_total" in result.detail, result.detail


def test_a_HANDLER_THAT_CAN_ARM_ITSELF_reddens_as_a_WIDENED_AUTHORITY(
    home: Path,
) -> None:
    """`StopArmPort` is the handler's INPUT. Satisfying it is arming authority."""
    _plant(
        home,
        _FILLS,
        "    def armed_orders(self) -> tuple[str, ...]:",
        "    def arm(self, fill_price: float, order: ProposedOrder) -> StopState:\n"
        '        """Planted: the handler can now convert its own stops."""\n'
        "        return self._stops.arm(fill_price, order)\n"
        "\n"
        "    def armed_orders(self) -> tuple[str, ...]:",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "SATISFIES StopArmPort, which it consumes" in result.detail, result.detail


def test_ACCEPTING_AN_UNAPPROVED_FILL_reddens(home: Path) -> None:
    """No approval ⇒ no sizer distance and no requested size. Refuse, loudly."""
    _plant(
        home,
        _FILLS,
        _REFUSE_UNAPPROVED,
        "        if False:  # planted: the refusal is gone\n"
        "            raise UnapprovedFill(",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "CO-NEVER-APPROVED" in result.detail, result.detail


# ==========================================================================
# THE INSTRUMENT'S OWN LIMITS — an unread subject is never a PASS
# ==========================================================================


def test_a_TREE_WITHOUT_THE_SUBJECT_is_CANNOT_MEASURE_not_a_FALL_THROUGH(
    tmp_path: Path,
) -> None:
    """D3.124: `_preamble` leaves the REAL scripts/ on sys.path forever."""
    result = _run(tmp_path)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "scripts/nixrisk/fills.py" in result.detail, result.detail
    assert "never a PASS" in result.detail, result.detail


def test_an_ABSENT_BROKER_SEAM_is_CANNOT_MEASURE_not_a_FREE_PASS(home: Path) -> None:
    """No §2A reference side means no statement about the production entry point."""
    (home / "scripts/broker/broker_seam.py").unlink()

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "broker_seam.py" in result.detail, result.detail


def test_an_ABSENT_CAP_CONFIG_is_CANNOT_MEASURE_not_an_UNPRICED_PASS(
    home: Path,
) -> None:
    """Without the ceiling and the tick values, ARM CAP measures this gate only."""
    (home / "risks/allocator_caps.config.json").unlink()

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "allocator_caps.config.json" in result.detail, result.detail


# ==========================================================================
# THE LAST STEP — the unplanted copy is GREEN, so every red above is the plant
# ==========================================================================


def test_the_UNPLANTED_COPY_is_GREEN_so_every_RED_above_is_the_PLANT(
    home: Path,
) -> None:
    """Without this, the suite shows only that the gate can fail."""
    result = _run(home)

    assert result.status is Status.PASS, result
    assert "drove 4 confirmed fill(s)" in result.evidence, result.evidence
