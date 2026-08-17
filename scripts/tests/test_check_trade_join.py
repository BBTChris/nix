"""ARC 034 / sub-agent A — the can-fail suite for the trade-join gate.

Structure follows `nix_check_contract.md` §5.1: non-vacuity FIRST, then one plant
per DECLARED PROPERTY that must FAIL and NAME its site, then the plants removed
and the same population passing.

**No plant touches a production artifact** (doctrine C.8, CHECK-DEBT D3.189):
every can-fail builds a throwaway `nix_home` under `tmp_path` holding COPIES of
`scripts/nixrisk/join.py` and its import closure, perturbs the COPY, and drives
the SHIPPED gate's own bytes against it.

**THE TWO PLANTS THE ARC BRIEF NAMES** are both here and both must redden:

* `test_a_COLLIDING_MINT_reddens...` gives two distinct orders ONE `trade_id`.
  §3:159 keys the position table by it, so two rows under one key means the table
  is not keyed by it at all.
* `test_a_WRONG_REVERSE_LOOKUP_reddens...` returns a REAL origin belonging to a
  DIFFERENT order. **A join gate that only checked non-null is green on exactly
  this answer** — the value is present, well-formed and plausible, and it is
  wrong. That is the trap this gate exists to avoid, and this control is what
  proves it avoided it.

The suite also drives the identity collapse from three directions — the named
function, an anonymous callable with the same behaviour, and the DEFAULT policy
that a caller gets by writing nothing at all — because the hazard stated forwards
is not "somebody passes the degenerate mint" but "nobody passes anything".

**Every control asserts the REASON**, never the status alone (check contract v2
§11 / §18).
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# protected-access: the non-vacuity controls read the gate's OWN tally and
# population directly, because a floor asserted against a table restated in
# this file would go stale the moment the gate's population moved — which is
# the anchor doctrine C.4 rejects, one layer over.
# pylint: disable=protected-access

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
# APPENDED, never inserted at the front — loader.py's failure mode #8 note.
sys.path.append(str(REPO / "checks"))

import check_trade_join as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)

_COPIED = (
    "scripts/nixrisk/__init__.py",
    "scripts/nixrisk/seam.py",
    "scripts/nixrisk/picture.py",
    "scripts/nixrisk/execution.py",
    "scripts/nixrisk/positions.py",
    "scripts/nixrisk/join.py",
)

_JOIN = "scripts/nixrisk/join.py"
_POSITIONS = "scripts/nixrisk/positions.py"

#: Plant anchors, exact source text from the shipped modules.
_MINT_BODY = (
    "        trade_id = (\n"
    '            f"{self._prefix}-{next(self._seq):0{_SEQ_WIDTH}d}-{order.strategy_id}"\n'
    "        )"
)
_MINT_GUARD = "        if trade_id == order.client_order_id:"
_REVERSE = "        return self._by_trade.get(trade_id)"
_PROBE_COUNT = "_PROBE_ORDERS = 2"
_IDENTITY_FASTPATH = "    if policy is identity_trade_id:"
_REFUSE_CALL = "    _refuse_degenerate(policy)"


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """A throwaway tree carrying COPIES of the join and its import closure."""
    for rel in _COPIED:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / rel, tmp_path / rel)
    return tmp_path


def _run(nix_home: Path):
    return gate.run(Mode.VERIFY, Context(nix_home=nix_home, mode=Mode.VERIFY))


def _plant(where: Path, rel: str, old: str, new: str) -> None:
    """Perturb the COPY, asserting the anchor really was there."""
    path = where / rel
    source = path.read_text(encoding="utf-8")
    assert old in source, f"the plant anchor {old!r} is not in {rel}"
    path.write_text(source.replace(old, new, 1), encoding="utf-8")


def _neuter_factory_guards(where: Path) -> None:
    """Disable `production_origins`' own defences so a bad mint reaches the drive.

    §0a, and the reason it is a helper rather than a comment: the ARC 034 / 0.5
    audit measured fail-closed branches that were never driven because the gate's
    own doubles could not produce the input. Here the SUBJECT defends itself twice
    — a named fast path and a behavioural probe — so a plant aimed at the ROUND
    TRIP would otherwise be swallowed by the factory and the round-trip arms would
    never see a wrong mapping at all.
    """
    _plant(
        where,
        _JOIN,
        _IDENTITY_FASTPATH,
        "    if policy is None:  # planted: the named fast path is disabled",
    )
    _plant(
        where,
        _JOIN,
        _REFUSE_CALL,
        "    _ = _refuse_degenerate  # planted: the behavioural probe is disabled",
    )


# ==========================================================================
# NON-VACUITY FIRST
# ==========================================================================


def test_the_REAL_TREE_passes_and_the_EVIDENCE_names_what_was_MEASURED() -> None:
    """The credibility floor: the figures are in evidence, not a restatement."""
    result = _run(REPO)

    assert result.status is Status.PASS, result
    assert "recorded 4 order(s)" in result.evidence, result.evidence
    assert "4 round trip(s) CLOSED" in result.evidence, result.evidence
    assert "3 degenerate policy/policies DRIVEN into a refusal" in result.evidence
    assert "UNBOUND" in result.evidence, result.evidence


def test_EVERY_DECLARED_FLOOR_IS_STRICTLY_BELOW_TODAYS_FIGURE() -> None:
    """Doctrine C.4: a threshold at today's number is an anchor that moves."""
    defects, tally, refusal = gate._measure(REPO)

    assert not defects, defects
    assert tally is not None, refusal
    for observed, floor, what in (
        (tally.orders, gate.MIN_ORDERS, "orders"),
        (tally.distinct_trade_ids, gate.MIN_DISTINCT_TRADE_IDS, "distinct ids"),
        (tally.round_trips, gate.MIN_ROUND_TRIPS, "round trips"),
        (tally.refusals_driven, gate.MIN_REFUSALS_DRIVEN, "refusals driven"),
    ):
        assert floor > 0, what
        assert floor < observed, f"{what}: floor {floor} is not below {observed}"


def test_THE_POPULATION_CAN_EXPOSE_A_COLLISION_and_a_WRONG_REVERSE() -> None:
    """Two orders share a strategy, so a strategy-keyed mint collides them."""
    strategies = [row[1] for row in gate._ORDERS]

    assert len(gate._ORDERS) >= 2, gate._ORDERS
    assert len(set(strategies)) < len(strategies), strategies


def test_the_GATE_DECLARES_THE_JOIN_AS_A_SUBJECT_so_coverage_is_real() -> None:
    """`check_artifact_gate_coverage` counts SUBJECTS; an undeclared module is uncovered."""
    assert "scripts/nixrisk/join.py" in gate.SUBJECTS, gate.SUBJECTS


# ==========================================================================
# THE ROUND TRIP — the property a non-null check cannot see
# ==========================================================================


def test_a_WRONG_REVERSE_LOOKUP_reddens_though_the_ANSWER_IS_A_REAL_ORIGIN(
    home: Path,
) -> None:
    """THE TRAP. The lookup is non-null, well-formed, plausible, and WRONG."""
    _plant(
        home,
        _POSITIONS,
        _REVERSE,
        "        del trade_id  # planted: always the FIRST origin recorded\n"
        "        return next(iter(self._by_trade.values()), None)",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "the round trip is OPEN" in result.detail.replace("\n", " "), result.detail
    assert "resolves back to order" in result.detail, result.detail


def test_a_MISSING_REVERSE_DIRECTION_reddens_and_SAYS_WHICH_TRADE(home: Path) -> None:
    """A reverse lookup that answers `None` leaves §3's key pointing at nothing."""
    _plant(
        home,
        _POSITIONS,
        _REVERSE,
        "        del trade_id  # planted: the reverse direction is gone\n"
        "        return None",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "resolves to NO origin" in result.detail, result.detail


def test_a_WRONG_FORWARD_LOOKUP_reddens_as_TWO_DIRECTIONS_DISAGREEING(
    home: Path,
) -> None:
    """§0a: the reverse plant alone leaves the forward branch undriven."""
    _plant(
        home,
        _POSITIONS,
        "        return self._by_order.get(client_order_id)",
        "        del client_order_id  # planted: always the FIRST origin\n"
        "        return next(iter(self._by_order.values()), None)",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "the two directions of the join disagree" in result.detail, result.detail


def test_a_DRIFTED_STRATEGY_ON_THE_JOIN_reddens_though_BOTH_KEYS_ROUND_TRIP(
    home: Path,
) -> None:
    """§9 requires strategy_id on every row and it rides the origin, not a lookup."""
    _plant(
        home,
        _POSITIONS,
        "        return self._by_order.get(client_order_id)",
        "        origin = self._by_order.get(client_order_id)\n"
        "        if origin is None:\n"
        "            return None\n"
        '        return dataclasses.replace(origin, strategy_id="PLANTED")',
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "the join carries strategy 'PLANTED'" in result.detail, result.detail


def test_a_REGISTRY_THAT_MISCOUNTS_ITSELF_reddens(home: Path) -> None:
    """A registry that cannot say what it holds can only be believed."""
    _plant(
        home,
        _POSITIONS,
        "        self.recorded += 1",
        "        pass  # planted: the observable stops observing",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "recorded origin(s) against 4 driven" in result.detail, result.detail


def test_a_COLLIDING_MINT_reddens_and_NAMES_the_key_that_is_not_a_key(
    home: Path,
) -> None:
    """Two orders, one `trade_id`. §3:159's table stops being keyed by it."""
    _neuter_factory_guards(home)
    _plant(
        home,
        _JOIN,
        _MINT_BODY,
        '        trade_id = "TRD-COLLIDED"  # planted: one id for every order',
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    # `EntryOrderOrigins.record` refuses the second collision at record time, so
    # the gate reports it as a subject defect naming the duplicate — the arm that
    # fires is the drive guard, and the REASON is what is asserted.
    assert "TRD-COLLIDED" in result.detail, result.detail


def test_an_IDENTITY_MINT_REACHING_THE_REGISTRY_reddens_per_order(
    home: Path,
) -> None:
    """Under the identity the round trip passes on EVERY input, so it must be caught."""
    _neuter_factory_guards(home)
    _plant(
        home,
        _JOIN,
        _MINT_GUARD,
        "        if trade_id is None:  # planted: the mint's own guard is off",
    )
    _plant(
        home,
        _JOIN,
        _MINT_BODY,
        "        next(self._seq)\n        trade_id = order.client_order_id",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "IS the client_order_id" in result.detail, result.detail
    assert "passes on every possible input" in result.detail, result.detail


# ==========================================================================
# UNREACHABILITY — the degenerate mint may not become the production policy
# ==========================================================================


def test_a_FACTORY_THAT_ACCEPTS_identity_trade_id_reddens_and_NAMES_IT(
    home: Path,
) -> None:
    """A named fast path alone is not the guarantee; removing both must redden."""
    _neuter_factory_guards(home)

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "identity_trade_id" in result.detail, result.detail
    assert "was ACCEPTED as the production join policy" in result.detail, result.detail


def test_a_NAME_ONLY_REFUSAL_reddens_on_the_ANONYMOUS_identity(home: Path) -> None:
    """`policy is identity_trade_id` is defeated by the same behaviour renamed.

    Only the behavioural probe is removed here; the named fast path stays. The
    gate must still redden, because the anonymous callable collapses the join
    exactly as completely and no identity comparison can see it.
    """
    _plant(
        home,
        _JOIN,
        _REFUSE_CALL,
        "    _ = _refuse_degenerate  # planted: only the PROBE is disabled",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "an anonymous identity mint" in result.detail, result.detail
    assert "a colliding constant mint" in result.detail, result.detail
    # The NAMED policy is still refused, which is what shows the probe — not the
    # name comparison — is the half that was doing the work.
    assert "[identity_trade_id]" not in result.site, result.site


def test_a_ONE_ORDER_PROBE_reddens_because_it_CANNOT_SEE_A_COLLISION(
    home: Path,
) -> None:
    """§7.12: one probe proves non-identity and proves NOTHING about injectivity."""
    _plant(home, _JOIN, _PROBE_COUNT, "_PROBE_ORDERS = 1")

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "a colliding constant mint" in result.detail, result.detail
    assert "TRD-CONSTANT" in result.detail, result.detail


def test_a_DEFAULT_POLICY_THAT_COLLAPSES_reddens_even_with_the_probes_intact(
    home: Path,
) -> None:
    """The hazard forwards: nobody passes anything and the default becomes policy."""
    _plant(
        home,
        _JOIN,
        "    if mint is None:\n        return SequencedTradeIdMint().mint",
        "    if mint is None:\n        return identity_trade_id  # planted default",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "identity_trade_id" in result.detail, result.detail


# ==========================================================================
# THE INSTRUMENT'S OWN LIMITS — an unread subject is never a PASS
# ==========================================================================


def test_a_TREE_WITHOUT_THE_SUBJECT_is_CANNOT_MEASURE_not_a_FALL_THROUGH(
    tmp_path: Path,
) -> None:
    """D3.124: `_preamble` leaves the REAL scripts/ on sys.path forever."""
    result = _run(tmp_path)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "scripts/nixrisk/join.py" in result.detail, result.detail
    assert "never a PASS" in result.detail, result.detail


def test_an_UNIMPORTABLE_SUBJECT_is_CANNOT_MEASURE_and_NAMES_the_exception(
    home: Path,
) -> None:
    """A subject that will not import was not read, so nothing was measured."""
    (home / _JOIN).write_text("def broken(:\n", encoding="utf-8")

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "SyntaxError" in result.detail, result.detail


# ==========================================================================
# THE LAST STEP — the unplanted copy is GREEN, so every red above is the plant
# ==========================================================================


def test_the_UNPLANTED_COPY_is_GREEN_so_every_RED_above_is_the_PLANT(
    home: Path,
) -> None:
    """Without this, the suite shows only that the gate can fail."""
    result = _run(home)

    assert result.status is Status.PASS, result
    assert "4 round trip(s) CLOSED" in result.evidence, result.evidence
