"""ARC 033 / 0.2 — the can-fail suite for the origin-write gate.

Structure follows `nix_check_contract.md` §5.1 / the `check_execution_ledger`
pattern: non-vacuity FIRST, then plants that must FAIL and NAME their site, then
the plants removed and the same population passing. A demonstration missing the
last step shows only that a gate can fail.

**No plant touches a production artifact** (doctrine C.8). Every can-fail builds
a throwaway `nix_home` under `tmp_path` holding COPIES of the real writer and
its real collaborators, perturbs the COPY, and drives the SHIPPED gate's own
bytes against it. `scripts/nixrisk/positions.py` is read and never written.

**EVERY PLANT IS IN THE SUBJECT, NEVER IN THE INPUT.** A fill stream doctored to
produce a wrong distance would prove nothing about the writer — any stream
produces what its inputs imply. The defects here are edits to the writer's own
bytes, and the input population is the gate's own, untouched.

**THE PLANT THAT MATTERS MOST is the one that is present, positive, plausible
and WRONG:** `test_a_WRONG_JOIN_publishing_ANOTHER_TRADES_REAL_DISTANCE_reddens`
makes the writer publish the first armed stop's distance for every trade. Every
published figure is a real stop distance, in ticks, of the right order of
magnitude, and non-null — a gate that only checked the field was populated would
be green over it.

**THE SECOND-MOST IMPORTANT is the one no drive can see:**
`test_a_FALLBACK_TO_THE_ORDERS_OWN_COPY_reddens_while_every_DRIVE_stays_green`
adds a defensive `distance or report.stop_ticks` fallback. The population never
enters it, so every behavioural arm of this gate and every test in
`test_positions.py` stays green — and ARM STRUCTURE still reddens. That plant is
doctrine C.9's question about this gate, driven rather than argued.
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code,protected-access
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

import check_origin_write as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)

#: Everything the writer needs, copied into the throwaway tree.
_COPIED = (
    "scripts/nixrisk/__init__.py",
    "scripts/nixrisk/seam.py",
    "scripts/nixrisk/picture.py",
    "scripts/nixrisk/execution.py",
    "scripts/nixrisk/stops.py",
    gate.WRITER,
)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """A throwaway tree carrying COPIES of the writer and its collaborators."""
    (tmp_path / "scripts" / "nixrisk").mkdir(parents=True)
    for rel in _COPIED:
        shutil.copy(REPO / rel, tmp_path / rel)
    return tmp_path


def _run(nix_home: Path):
    return gate.run(Mode.VERIFY, Context(nix_home=nix_home, mode=Mode.VERIFY))


def _plant(home: Path, old: str, new: str) -> None:
    """Rewrite the COPIED writer. Fails loudly if the anchor moved."""
    path = home / gate.WRITER
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"anchor appears {text.count(old)} times, not once"
    path.write_text(text.replace(old, new), encoding="utf-8")


# The anchors, spelled once. Each is a real line of the shipped writer.
_LOOKUP_ANCHOR = "        stop = self._stops.get(origin.client_order_id)\n"
_REFUSE_ANCHOR = (
    "        if stop is None:\n"
    "            self._refuse_unstopped(report, origin)\n"
    "        distance = stop.initial_distance_ticks\n"
)
_TRADE_ID_ANCHOR = (
    "        return PositionRow(\n            trade_id=origin.trade_id,\n"
)
_DISTANCE_ANCHOR = "            stop_distance=distance,\n"
_COMMIT_ANCHOR = (
    "        picture = self._picture.commit(\n"
    "            positions=self._merged(row), sum_reservations=sum_reservations\n"
    "        )\n"
)
_CUMULATIVE_ANCHOR = "        filled = self._ledger.order_cumulative(report.order_id)\n"
_RAISE_ANCHOR = "        raise UnstoppedFill(\n"
_RECORD_ANCHOR = "        self._unstopped.append(\n"
_MERGE_ANCHOR = (
    "        if any(existing.trade_id == row.trade_id for existing in current):\n"
)


# --------------------------------------------------------------------------
# NON-VACUITY FIRST — the gate reaches a real writer and a real population
# --------------------------------------------------------------------------


def test_the_REAL_TREE_passes_and_the_EVIDENCE_names_what_was_DRIVEN() -> None:
    """The credibility floor: real trades, real distances, real refusals.

    The counts are DERIVED from the gate's own population constants rather than
    typed, for the reason `test_check_execution_ledger` records: a literal here
    goes stale inside the arc that widens the population, which is exactly the
    restatement directive 3 forbids.
    """
    result = _run(REPO)

    assert result.status is Status.PASS, result
    assert f"{len(gate._ORDERS)} trade(s) compared" in result.evidence
    assert f"{len(gate._UNSTOPPED)} confirmed fill(s) with no armed stop" in (
        result.evidence
    )
    assert f"{len(gate._PARTIALS)} partially-filled order(s)" in result.evidence
    assert "UNBOUND" in result.evidence


def test_the_COPY_under_tmp_path_passes_too_so_a_PLANT_is_the_only_difference(
    home: Path,
) -> None:
    """Every plant below is measured against THIS green, not against the repo."""
    result = _run(home)

    assert result.status is Status.PASS, result


def test_the_POPULATION_carries_PAIRWISE_DISTINCT_NONZERO_distances() -> None:
    """Rule 3 of the gate's own §7.12 block, asserted rather than trusted."""
    distances = [row[5] for row in gate._ORDERS]

    assert len(set(distances)) == len(distances)
    assert all(distance > 0 for distance in distances)
    assert not set(distances) & {row[4] for row in gate._ORDERS}


def test_the_FLOORS_are_FLOORS_and_not_TODAYS_COUNTS() -> None:
    """Doctrine C.4: a threshold equal to today's number is an anchor that moves."""
    assert gate.MIN_TRADES < len(gate._ORDERS)
    assert gate.MIN_SYMBOLS < len({row[2] for row in gate._ORDERS})
    assert gate.MIN_DISTINCT_DISTANCES < len({row[5] for row in gate._ORDERS})
    assert gate.MIN_PARTIAL_ORDERS < len(gate._PARTIALS)
    assert gate.MIN_UNSTOPPED_DRIVES < len(gate._UNSTOPPED)
    assert gate.MIN_NON_IDENTITY_TRADES < len(gate._ORDERS)


# --------------------------------------------------------------------------
# THE §0a PLANT — present, positive, plausible, and WRONG
# --------------------------------------------------------------------------


def test_a_WRONG_JOIN_publishing_ANOTHER_TRADES_REAL_DISTANCE_reddens(
    home: Path,
) -> None:
    """The trap this gate exists for: the field is populated, and it is wrong.

    The plant reads the FIRST armed stop in the book instead of the one for this
    trade. Every published `stop_distance` is then a real, positive, plausible
    tick distance belonging to a real stop — and belongs to the wrong trade for
    every position but one. A gate that checked only for a non-null value would
    be green over this, which is why the comparison is PER TRADE against an
    independent reference over pairwise-distinct distances.
    """
    _plant(home, _LOOKUP_ANCHOR, "        stop = self._stops.stops()[0]\n")

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "PositionRow.stop_distance" in result.site
    # The published figure is REAL and POSITIVE — the reason must show both
    # numbers, not merely say "mismatch".
    wrong = gate._ORDERS[0][5]
    for coid, _strategy, _symbol, _long, _qty, expected, _price in gate._ORDERS[1:]:
        assert f"trade {coid!r}" in result.detail
        assert f"stop_distance={wrong!r}" in result.detail
        assert f"reference says {expected!r}" in result.detail
    assert "§7:501" in result.detail
    assert "belongs to another trade" in result.detail


def test_a_LITERAL_stop_distance_reddens_as_D3_150s_own_finding(home: Path) -> None:
    """A placeholder is indistinguishable from a considered figure."""
    _plant(home, _DISTANCE_ANCHOR, "            stop_distance=20,\n")

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "PositionRow(...)" in result.site
    assert "the LITERAL 20" in result.detail
    assert "D3.150" in result.detail


# --------------------------------------------------------------------------
# THE PLANT NO DRIVE CAN SEE
# --------------------------------------------------------------------------


def test_a_FALLBACK_TO_THE_ORDERS_OWN_COPY_reddens_while_every_DRIVE_stays_green(
    home: Path,
) -> None:
    """`StopBook.arm` records the stop book's distance FROM the order's, so the
    two agree on every drive that can be built — and diverge the moment a stop is
    amended. This plant is a defensive fallback the population never enters: all
    six behavioural arms stay green over it and ARM STRUCTURE still reddens.
    """
    _plant(
        home,
        _DISTANCE_ANCHOR,
        "            stop_distance=distance or report.stop_ticks,\n",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert result.site == f"{gate.WRITER}:PositionRow(...)"  # ONLY the static arm
    assert "reads ProposedOrder.stop_ticks" in result.detail
    assert "NO behavioural arm can separate them" in result.detail


def test_ABANDONING_the_STOP_BOOKS_FIELD_reddens_even_where_a_drive_agrees(
    home: Path,
) -> None:
    """The module must READ `initial_distance_ticks`; nothing else is the stop."""
    _plant(
        home,
        _REFUSE_ANCHOR,
        "        if stop is None:\n"
        "            self._refuse_unstopped(report, origin)\n"
        "        distance = getattr(stop, 'initial_' + 'distance_ticks')\n",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "never reads StopState.initial_distance_ticks" in result.detail


# --------------------------------------------------------------------------
# THE JOIN — an equality where the injected surface belongs
# --------------------------------------------------------------------------


def test_a_HARD_CODED_IDENTITY_JOIN_reddens_on_BOTH_the_drive_and_the_shape(
    home: Path,
) -> None:
    """`trade_id = order_id` is byte-identical to correct under the default
    binding, which is exactly why the gate drives a NON-IDENTITY mint as well."""
    _plant(
        home,
        _TRADE_ID_ANCHOR,
        "        return PositionRow(\n            trade_id=report.order_id,\n",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert f"{gate.WRITER}:PositionRow.trade_id" in result.site
    assert f"{gate.WRITER}:PositionRow(...)" in result.site
    # The behavioural half: the non-identity mint's key never reaches the table.
    assert gate._MINT_PREFIX in result.detail
    assert "INDISTINGUISHABLE from correct under the default binding" in result.detail
    # The structural half: the decision was buried in an equality.
    assert "buries an architectural decision" in result.detail


# --------------------------------------------------------------------------
# FAIL-CLOSED — the unstopped fill
# --------------------------------------------------------------------------


def test_DEFAULTING_an_UNSTOPPED_FILL_TO_ZERO_reddens_as_the_D3_136_FAIL_OPEN(
    home: Path,
) -> None:
    """The exact fail-open D3.136 named, in its new spelling."""
    _plant(
        home,
        _REFUSE_ANCHOR,
        "        distance = stop.initial_distance_ticks if stop is not None else 0\n",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "on_fill[no armed stop]" in result.site
    assert "the writer PUBLISHED anyway" in result.detail
    assert "ADMITS MORE" in result.detail
    assert "=0" in result.detail  # the zero distance, shown


def test_a_REFUSAL_OF_THE_WRONG_TYPE_reddens_because_a_CALLER_cannot_tell(
    home: Path,
) -> None:
    """§18: an exception type is a shared namespace; the reason is the evidence."""
    _plant(home, _RAISE_ANCHOR, "        raise OriginError(\n")

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "on_fill[no armed stop]" in result.site
    assert "must be the module's own UnstoppedFill" in result.detail


def test_a_REFUSAL_THAT_VANISHES_reddens_because_NOTHING_can_FLATTEN_it(
    home: Path,
) -> None:
    """§14 resolves an unprotected position toward FLAT; it must be visible."""
    _plant(home, _RECORD_ANCHOR, "        [].append(\n")

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "not recorded in unstopped()" in result.detail
    assert "UNPROTECTED position" in result.detail


# --------------------------------------------------------------------------
# THE LEDGER AND THE SNAPSHOT
# --------------------------------------------------------------------------


def test_PUBLISHING_THE_LAST_INCREMENT_instead_of_the_CUMULATIVE_reddens(
    home: Path,
) -> None:
    """Doctrine C.9: §4's ledger owns position, and this is what asking it buys."""
    _plant(home, _CUMULATIVE_ANCHOR, "        filled = report.filled_qty\n")

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "on_fill[cumulative]" in result.site
    assert "ACTUAL filled quantity" in result.detail
    assert "shows the last increment" in result.detail


def test_A_ROW_THAT_NEVER_RIDES_THE_COMMIT_reddens_as_a_SECOND_TABLE(
    home: Path,
) -> None:
    """§3's one snapshot, §9's sole writer: a row published anywhere else is not
    the financial picture the Allocator mirrors."""
    _plant(home, _COMMIT_ANCHOR, "        picture = self._picture.current()\n")

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "has NO published row" in result.detail
    assert "priced at zero by OMISSION" in result.detail


def test_A_SECOND_ROW_PER_TRADE_reddens_because_the_TABLE_IS_KEYED_BY_TRADE(
    home: Path,
) -> None:
    """A partial fill appending rather than replacing double-counts the position."""
    _plant(home, _MERGE_ANCHOR, "        if False:\n")

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "keys the position table BY trade_id" in result.detail


# --------------------------------------------------------------------------
# THE GATE'S OWN GUARDS — never a PASS over a broken instrument (§17)
# --------------------------------------------------------------------------


def test_a_DEGENERATE_POPULATION_SHARING_ONE_DISTANCE_is_CANNOT_MEASURE(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A wrong join publishes the right number by luck; refuse before measuring."""
    shared = tuple(
        (coid, strategy, symbol, is_long, qty, 13, price)
        for coid, strategy, symbol, is_long, qty, _stop, price in gate._ORDERS
    )
    monkeypatch.setattr(gate, "_ORDERS", shared)

    result = _run(REPO)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "share a stop distance" in result.detail
    assert "by luck" in result.detail


def test_a_ZERO_REFERENCE_DISTANCE_is_CANNOT_MEASURE_not_a_PASS(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A zero reference would agree with the very fail-open being hunted."""
    zeroed = tuple(
        (coid, strategy, symbol, is_long, qty, 0, price)
        for coid, strategy, symbol, is_long, qty, _stop, price in gate._ORDERS
    )
    monkeypatch.setattr(gate, "_ORDERS", zeroed)

    result = _run(REPO)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "would let a writer publishing zero" in result.detail


def test_a_SINGLE_TRADE_POPULATION_is_CANNOT_MEASURE_naming_the_FLOOR(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One trade cannot expose a wrong join: any join maps the only row."""
    monkeypatch.setattr(gate, "_ORDERS", gate._ORDERS[:1])

    result = _run(REPO)

    assert result.status is Status.CANNOT_MEASURE, result
    assert f"below the floor of {gate.MIN_TRADES}" in result.detail
    assert "cannot expose a wrong join" in result.detail


def test_a_DISTANCE_COLLIDING_WITH_A_SIZE_is_CANNOT_MEASURE(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A writer publishing `size` where the distance belongs would agree."""
    collided = tuple(
        (coid, strategy, symbol, is_long, qty, qty, price)
        for coid, strategy, symbol, is_long, qty, _stop, price in gate._ORDERS
    )
    monkeypatch.setattr(gate, "_ORDERS", collided)

    result = _run(REPO)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "coincides with a position size" in result.detail


def test_AN_UNIMPORTABLE_SUBJECT_is_CANNOT_MEASURE_naming_it_never_a_PASS(
    home: Path,
) -> None:
    """§17: a property proven while its subject is unavailable is not proven."""
    (home / gate.WRITER).unlink()

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "cannot import nixrisk.positions" in result.detail
    assert "§17" in result.detail


def test_AN_EMPTY_TREE_is_CANNOT_MEASURE_because_the_IMPORT_FELL_THROUGH(
    tmp_path: Path,
) -> None:
    """D3.124: `_preamble` leaves the REAL `scripts/` on `sys.path` forever, so
    an import against a tree without the subject silently resolves against this
    repository and the gate would report on a tree it never read."""
    result = _run(tmp_path)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "not from the" in result.detail or "is NOT under" in result.detail
    assert "§17" in result.detail


def test_a_BROKEN_REFERENCE_BOOK_is_CANNOT_MEASURE_about_the_INSTRUMENT(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A literal that disagrees with the shipped conversion is this gate's fault,
    and must not be reported as the writer's."""
    monkeypatch.setattr(gate, "_TICKS", {"ESZ6": 0.25})

    result = _run(REPO)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "reference stop book could not be armed" in result.detail
    assert "not about the writer" in result.detail


def test_A_SUBJECT_THAT_RAISES_is_the_SUBJECTS_defect_not_the_INSTRUMENTS(
    home: Path,
) -> None:
    """§18's shared namespace: a legitimate drive that raises is a FAIL, not a
    CANNOT_MEASURE — reporting "the instrument broke" over a broken subject is
    the exact confusion the rule exists to stop."""
    _plant(
        home,
        _LOOKUP_ANCHOR,
        "        raise RuntimeError('planted: the writer refuses every fill')\n",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "planted: the writer refuses every fill" in result.detail
    assert "is the writer's defect" in result.detail


# --------------------------------------------------------------------------
# THE PLANTS REMOVED — the same population passing
# --------------------------------------------------------------------------


def test_the_PLANTS_REMOVED_and_the_SAME_POPULATION_PASSING(home: Path) -> None:
    """A demonstration missing this step shows only that a gate can fail."""
    _plant(home, _LOOKUP_ANCHOR, "        stop = self._stops.stops()[0]\n")
    assert _run(home).status is Status.FAIL_NEEDS_OPERATOR

    shutil.copy(REPO / gate.WRITER, home / gate.WRITER)

    result = _run(home)
    assert result.status is Status.PASS, result
    assert f"{len(gate._ORDERS)} trade(s) compared" in result.evidence
