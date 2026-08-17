"""The §6.6 seam gate must REDDEN on the three things Phase 0.4 froze.

The brief that commissioned this seam asked for exactly one proof: *"prove the
seam gate reddens on: a reader that computes instead of looks up; a fallback
that stalls instead of returning FCFS; a second writer to the ranking table."*
Those are the three headline arms below, and each is driven by BREAKING A REAL
COPY of the shipped seam and running the SHIPPED gate against the broken tree —
never by asserting that a detector function returns True.

Doctrine C.8: no plant touches a production artefact. Every broken seam is
written under `tmp_path`, and the gate is pointed at that home.

## §0a on this file: what would make it pass while measuring nothing?

Two answers, and both are arms here rather than notes:

  * **The gate could pass the honest seam and also pass every broken one.** So
    every plant arm is a PAIR — the same tree, the same gate, one edit apart —
    and the unbroken half is asserted green in the same test.
  * **The stall plant is the one that can go vacuous.** A fallback that stalls
    is invisible to any assertion about the RETURN VALUE, because the value is
    right; only elapsed time or the shape of the code shows it. Both are driven,
    and the timing plant asserts the measured worst case actually exceeded the
    budget rather than merely that the gate went red — otherwise the arm would
    pass on a red raised for some unrelated reason.
"""

# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# pylint: disable=missing-function-docstring
# Test names spell the OUTCOME. The sys.path bootstrap is repeated per module
# deliberately; one shared helper would let a single edit un-bind several.
from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parents[2]
for _extra in (str(REPO / "checks"), str(REPO / "scripts")):
    if _extra not in sys.path:
        sys.path.insert(0, _extra)

# pylint: disable=wrong-import-position
import check_scoring_seam as gate  # pylint: disable=import-error
from nixbus.statebus import StateMessage  # pylint: disable=import-error
from nixscore import seam  # pylint: disable=import-error
from nixverify.contract import Context, Mode, Status  # pylint: disable=import-error

SEAM_SRC = REPO / gate.SEAM_MODULE


# ---------------------------------------------------------------------------
# A throwaway home holding a REAL copy of the seam the gate can be pointed at
# ---------------------------------------------------------------------------


@pytest.fixture()
def home(tmp_path: Path) -> Path:
    """A tree with `scripts/nixscore/` and `scripts/nixbus/` copied in.

    The gate imports the seam from the home it is given, so a broken copy here
    is genuinely the subject under test — not a monkeypatched attribute on the
    shipped module, which would prove the gate reads a name rather than a tree.
    """
    dst = tmp_path / "nix"
    (dst / "scripts").mkdir(parents=True)
    shutil.copytree(REPO / "scripts" / "nixscore", dst / "scripts" / "nixscore")
    shutil.copytree(
        REPO / "scripts" / "nixbus",
        dst / "scripts" / "nixbus",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    return dst


def _run(home: Path):
    """Run the SHIPPED gate against `home`, with a clean import of its seam."""
    for name in [m for m in sys.modules if m.startswith("nixscore")]:
        del sys.modules[name]
    scripts = str(home / "scripts")
    sys.path.insert(0, scripts)
    try:
        return gate.run(Mode.VERIFY, Context(nix_home=home, mode=Mode.VERIFY))
    finally:
        while scripts in sys.path:
            sys.path.remove(scripts)
        for name in [m for m in sys.modules if m.startswith("nixscore")]:
            del sys.modules[name]


def _break(home: Path, old: str, new: str) -> None:
    """One textual edit to the copied seam, asserted to have landed."""
    target = home / gate.SEAM_MODULE
    text = target.read_text(encoding="utf-8")
    assert old in text, f"plant anchor {old!r} is not in the copied seam"
    broken = text.replace(old, new, 1)
    assert broken != text, "the plant changed nothing"
    target.write_text(broken, encoding="utf-8")


# ---------------------------------------------------------------------------
# The unbroken half — asserted first, so every plant below is a PAIR
# ---------------------------------------------------------------------------


def test_the_gate_PASSES_the_seam_as_frozen(home: Path) -> None:
    result = _run(home)
    assert result.status is Status.PASS, result.detail
    assert "five documented FCFS triggers" in (result.evidence or "")


# ---------------------------------------------------------------------------
# PLANT 1 — a reader that COMPUTES instead of looking up
# ---------------------------------------------------------------------------


def test_the_gate_REDDENS_on_a_reader_that_computes_instead_of_looking_up(
    home: Path,
) -> None:
    """§6.6: nobody but the Scoring process computes the score.

    The planted reader returns a CORRECT row. It is not wrong; it is a reader
    doing the allocation judgment §6.6 keeps out of the gate, and no assertion
    about its output could tell.
    """
    _break(
        home,
        '        """THE HOT-PATH READ. One dict get. No arithmetic, no I/O, no scan."""\n'
        "        return self._rows.get((strategy_id, symbol))",
        '        """A reader recomputing the ranking. The §11 hot-path violation."""\n'
        "        ordered = sorted(self._rows.values(), key=lambda r: -r.realized_ema)\n"
        "        for position, row in enumerate(ordered, start=1):\n"
        "            if row.strategy_id == strategy_id and row.symbol == symbol:\n"
        "                return row\n"
        "        return None",
    )
    result = _run(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.evidence
    detail = result.detail or ""
    assert "lookup" in detail, detail
    assert "O(1)" in detail or "sorted" in detail, (
        "the finding must name WHAT it saw on the read path, not merely that "
        "the seam failed (check contract §18)"
    )


def test_the_gate_REDDENS_when_a_reader_calls_the_ranking_function_itself(
    home: Path,
) -> None:
    """`rank_rows` is legitimate exactly once, in Scoring, before publish."""
    _break(
        home,
        "        return self._rows.get((strategy_id, symbol))",
        "        return rank_rows({}).get((strategy_id, symbol))",
    )
    result = _run(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "rank_rows" in (result.detail or ""), result.detail


# ---------------------------------------------------------------------------
# PLANT 2 — a fallback that STALLS instead of returning FCFS
# ---------------------------------------------------------------------------


def test_the_gate_REDDENS_on_a_fallback_that_can_block(home: Path) -> None:
    """The value is right and the latency is fatal.

    §6.6: *"a scoring outage must NEVER halt order flow."* This plant returns
    the correct FCFS verdict — after spinning. Every assertion about the verdict
    passes; the shape arm is what sees it.
    """
    _break(
        home,
        "        if self._applied_at is None:\n"
        "            return Verdict(\n"
        "                Arbitration.FCFS,",
        "        while self._applied_at is None and self.applied < 0:\n"
        "            pass\n"
        "        if self._applied_at is None:\n"
        "            return Verdict(\n"
        "                Arbitration.FCFS,",
    )
    result = _run(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    detail = result.detail or ""
    assert "arbitrate" in detail and "While" in detail, detail


def test_the_gate_REDDENS_on_a_fallback_that_raises_instead_of_answering(
    home: Path,
) -> None:
    """An exception out of the arbitration path is a stall wearing a traceback."""
    _break(
        home,
        "        left = self._rows.get(first)\n        right = self._rows.get(second)",
        "        left = self._rows.get(first)\n"
        "        right = self._rows.get(second)\n"
        "        if left is None:\n"
        "            raise SeamError('no row')",
    )
    result = _run(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "can raise" in (result.detail or ""), result.detail


def test_the_TIMING_arm_measures_a_real_stall_and_not_merely_a_red() -> None:
    """The timing arm's own can-fail, driven at the numbers.

    Asserting only that the gate went red would let this arm pass on a red
    raised for an unrelated reason. What is asserted is the MEASUREMENT: a
    reader that sleeps must produce a worst case above the budget, and the
    honest mirror must produce one below it.
    """

    class Stalling:  # pylint: disable=too-few-public-methods
        """A reader with the right answer and the wrong latency."""

        def arbitrate(self, first, second, now=None):
            """Sleep, then answer."""  # pylint: disable=unused-argument
            time.sleep(gate.ARBITRATION_BUDGET_S * 3)

    stalled = gate.worst_arbitration_s(Stalling(), ("a", "b"), ("c", "d"), drives=2)
    assert stalled > gate.ARBITRATION_BUDGET_S, stalled

    mirror = seam.RankingMirror(stale_after_s=5.0)
    honest = gate.worst_arbitration_s(mirror, ("a", "b"), ("c", "d"), drives=50)
    assert honest < gate.ARBITRATION_BUDGET_S, (
        f"the honest fallback measured {honest * 1000:.3f}ms — if the budget "
        "cannot separate it from a sleeping reader, the arm proves nothing"
    )

    can_fail, why = gate.timing_arm_can_fail()
    assert can_fail, why


# ---------------------------------------------------------------------------
# PLANT 3 — a SECOND WRITER to the ranking table
# ---------------------------------------------------------------------------


def test_the_gate_REDDENS_when_the_mirror_accepts_a_foreign_writer(
    home: Path,
) -> None:
    """§6.6 makes Scoring the sole writer, and the consumer is where it lands."""
    _break(
        home,
        "        if snapshot.writer_identity != self.identity:\n"
        "            self.foreign_rejected += 1\n"
        "            return False",
        "        # PLANT: any publisher's snapshot becomes this consumer's table.\n"
        "        if False:\n"
        "            self.foreign_rejected += 1\n"
        "            return False",
    )
    result = _run(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "sole writer" in (result.detail or ""), result.detail


def test_the_gate_REDDENS_when_a_foreign_snapshot_is_dropped_SILENTLY(
    home: Path,
) -> None:
    """A silent drop reads exactly like a message that never arrived."""
    _break(
        home,
        "            self.foreign_rejected += 1\n            return False",
        "            return False",
    )
    result = _run(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "COUNTED" in (result.detail or ""), result.detail


def test_the_gate_REDDENS_when_the_mirror_grows_a_way_to_write_itself(
    home: Path,
) -> None:
    """§12.7: a consumer keeps a private read-only mirror it NEVER writes."""
    _break(
        home,
        "    def lookup(self, strategy_id: str, symbol: str) -> RankRow | None:",
        "    def set_row(self, key, row) -> None:\n"
        "        self._rows[key] = row\n\n"
        "    def lookup(self, strategy_id: str, symbol: str) -> RankRow | None:",
    )
    result = _run(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "set_row" in (result.detail or ""), result.detail


# ---------------------------------------------------------------------------
# The staleness plant — the silent failure C2 names
# ---------------------------------------------------------------------------


def test_the_gate_REDDENS_when_a_STALE_table_is_read_as_FRESH(home: Path) -> None:
    """A stale-but-present table read as fresh is the silent failure.

    The mirror still holds real rows and still answers instantly. It answers
    from a table that stopped being updated when Scoring died — which is worse
    than no table at all, because it is a confident wrong ranking rather than a
    fallback.
    """
    _break(
        home,
        "        age = self.age_s(now)\n"
        "        return age is not None and age <= self.stale_after_s",
        "        return self._applied_at is not None",
    )
    result = _run(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "stale" in (result.detail or "").lower(), result.detail


def test_the_gate_REDDENS_when_the_FCFS_winner_is_not_the_earlier_arrival(
    home: Path,
) -> None:
    """First-come-first-served IS the arrival order. Anything else is a preference."""
    _break(
        home,
        "            return Verdict(\n"
        "                Arbitration.FCFS,\n"
        "                first,\n"
        '                "no ranking snapshot has arrived',
        "            return Verdict(\n"
        "                Arbitration.FCFS,\n"
        "                second,\n"
        '                "no ranking snapshot has arrived',
    )
    result = _run(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "earlier arrival" in (result.detail or ""), result.detail


def test_the_gate_REDDENS_when_the_fallback_fires_with_no_reason(home: Path) -> None:
    """Five conditions reach FCFS; the outcome alone cannot tell them apart."""
    _break(
        home,
        '                "no ranking snapshot has arrived; §12.7 treats an incomplete "\n'
        '                "mirror as stale and §6.6 makes the degraded answer FCFS",',
        '                "",',
    )
    result = _run(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "no reason" in (result.detail or ""), result.detail


# ---------------------------------------------------------------------------
# NON-VACUITY — the scan must have a subject
# ---------------------------------------------------------------------------


def test_the_gate_reports_a_scan_that_lost_its_subject(home: Path) -> None:
    """A rename that empties the scan must be loud, not green."""
    _break(home, "    def arbitrate(\n", "    def arbitrate_renamed(\n")
    result = _run(home)
    assert result.status in (Status.FAIL_NEEDS_OPERATOR, Status.CANNOT_MEASURE)
    assert "non-vacuity" in (result.detail or "") or "arbitrate" in (
        result.detail or ""
    ), result.detail


def test_the_three_arms_prove_they_can_fail_on_the_shipped_gate() -> None:
    for label, control in (
        ("read-path", gate.read_path_arm_can_fail),
        ("shape", gate.stalling_arm_can_fail),
        ("timing", gate.timing_arm_can_fail),
    ):
        ok, why = control()
        assert ok, f"{label}: {why}"


# ---------------------------------------------------------------------------
# The seam's own behaviour, driven directly
# ---------------------------------------------------------------------------


def _feed(mirror, pairs, now, identity=None, seq=1):
    snapshot = seam.RankingSnapshot(
        rows=seam.rank_rows(pairs),
        span_days=10,
        writer_identity=identity or seam.SCORING_WRITER_IDENTITY,
    )
    return mirror.apply(
        StateMessage(seam.RANKING_TOPIC, snapshot.as_wire(), seq, now, True), now=now
    )


def test_a_ranking_snapshot_survives_the_wire_unchanged() -> None:
    rows = seam.rank_rows({("s1", "ES"): 500.0, ("s2", "NQ"): -20.5})
    snapshot = seam.RankingSnapshot(rows=rows, span_days=10)
    assert seam.RankingSnapshot.from_wire(snapshot.as_wire()).rows == rows


def test_a_pair_key_containing_the_delimiter_is_refused_not_silently_split() -> None:
    with pytest.raises(seam.SeamError):
        seam.wire_key(("s\0evil", "ES"))


def test_tied_pairs_share_a_rank_so_arbitration_falls_back_not_guesses() -> None:
    rows = seam.rank_rows({("a", "ES"): 5.0, ("b", "ES"): 5.0, ("c", "ES"): 1.0})
    assert rows[("a", "ES")].rank == rows[("b", "ES")].rank == 1
    assert rows[("c", "ES")].rank == 3


def test_a_never_fed_mirror_is_STALE_and_not_merely_empty() -> None:
    mirror = seam.RankingMirror(stale_after_s=5.0)
    assert not mirror.fresh()
    assert mirror.age_s() is None
    assert mirror.span_days is None


def test_a_non_positive_freshness_threshold_is_refused_at_construction() -> None:
    with pytest.raises(seam.SeamError):
        seam.RankingMirror(stale_after_s=0.0)


def test_the_publisher_refuses_to_stamp_a_snapshot_it_did_not_write() -> None:
    class _Sink:  # pylint: disable=too-few-public-methods
        """Captures what the publisher sent, with no transport."""

        def __init__(self):
            self.sent = []

        def publish(self, topic, payload):
            """Record one publish."""
            self.sent.append((topic, payload))

    sink = _Sink()
    publisher = seam.RankingPublisher(sink)
    honest = seam.RankingSnapshot(rows={}, span_days=10)
    publisher.publish(honest)
    assert publisher.published == 1
    forged = seam.RankingSnapshot(rows={}, span_days=10, writer_identity="impostor")
    with pytest.raises(seam.SeamError):
        publisher.publish(forged)
    assert publisher.published == 1, "the refused publish must not be counted"


@pytest.mark.parametrize(
    ("label", "setup", "expect_reason"),
    [
        ("never fed", lambda m: None, "no ranking snapshot has arrived"),
        (
            "absent row",
            lambda m: _feed(m, {("s1", "ES"): 9.0}, 100.0),
            "no ranking row",
        ),
        (
            "equal EMA",
            lambda m: _feed(m, {("s1", "ES"): 5.0, ("s2", "ES"): 5.0}, 100.0),
            "equal realized EMA",
        ),
        (
            "foreign writer",
            lambda m: _feed(m, {("s1", "ES"): 9.0, ("s2", "ES"): 1.0}, 100.0, "x"),
            "no ranking snapshot has arrived",
        ),
    ],
)
def test_every_FCFS_trigger_names_itself(label, setup, expect_reason) -> None:
    mirror = seam.RankingMirror(stale_after_s=5.0)
    setup(mirror)
    verdict = mirror.arbitrate(("s1", "ES"), ("s2", "ES"), now=100.5)
    assert verdict.outcome is seam.Arbitration.FCFS, label
    assert verdict.winner == ("s1", "ES"), f"{label}: FCFS is the earlier arrival"
    assert expect_reason in verdict.reason, f"{label}: {verdict.reason}"


def test_a_table_one_millisecond_past_the_threshold_falls_back() -> None:
    """The boundary, driven from both sides — not the middle of the range."""
    mirror = seam.RankingMirror(stale_after_s=5.0)
    _feed(mirror, {("s1", "ES"): 900.0, ("s2", "ES"): 1.0}, now=100.0)
    inside = mirror.arbitrate(("s1", "ES"), ("s2", "ES"), now=105.0)
    assert inside.outcome is seam.Arbitration.RANKED, inside.reason
    outside = mirror.arbitrate(("s1", "ES"), ("s2", "ES"), now=105.001)
    assert outside.outcome is seam.Arbitration.FCFS
    assert "stale" in outside.reason
