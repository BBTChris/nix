"""ARC 033 / 0.3 — the can-fail suite for the execution-ledger gate.

Structure follows `nix_check_contract.md` §5.1 / the `check_reservation_lifecycle`
pattern: non-vacuity FIRST, then plants that must FAIL and NAME their site, then
the plants removed and the same population passing. A demonstration missing the
last step shows only that a gate can fail.

**No plant touches a production artifact** (doctrine C.8). Every can-fail builds
a throwaway `nix_home` under `tmp_path` holding a COPY of the real ledger and the
real frozen seam, perturbs the COPY, and drives the SHIPPED gate's own bytes
against it. `scripts/nixrisk/execution.py` is read and never written.

**Every control asserts the REASON** — the site and the named condition — never
the exit code or the status alone (check contract v2 §11 / §18).

**THE PLANT THAT MATTERS MOST IS THE ONE NO DRIVE CAN SEE.**
`test_a_MAINTAINED_RUNNING_TOTAL_fails_even_though_every_DRIVE_stays_green`
plants a correctly-maintained per-symbol running total: it is permutation-
invariant, it is duplicate-immune, it reconciles, it audits — every behavioural
arm of this gate and every property `scripts/tests/test_execution.py` owns stays
green over it — and ARM STRUCTURE still reddens. That plant is the concrete
answer to doctrine C.9's question about this gate, driven rather than argued.
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
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

import check_execution_ledger as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)

SEAM = "scripts/nixrisk/seam.py"
INIT = "scripts/nixrisk/__init__.py"


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """A throwaway tree carrying COPIES of the ledger and the seam."""
    (tmp_path / "scripts" / "nixrisk").mkdir(parents=True)
    for rel in (gate.LEDGER, SEAM, INIT):
        shutil.copy(REPO / rel, tmp_path / rel)
    return tmp_path


def _run(nix_home: Path):
    return gate.run(Mode.VERIFY, Context(nix_home=nix_home, mode=Mode.VERIFY))


def _plant(home: Path, old: str, new: str) -> None:
    """Rewrite the COPIED ledger. Fails loudly if the anchor moved."""
    path = home / gate.LEDGER
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"anchor appears {text.count(old)} times, not once"
    path.write_text(text.replace(old, new), encoding="utf-8")


# The anchors, spelled once. Each is a real line of the shipped ledger.
_DEDUP_ANCHOR = (
    "        prior = self._fills.get(report.key)\n"
    "        if prior is not None:\n"
    "            return self._on_duplicate_key(prior, report)\n"
    "        self._guard_order_consistency(report)\n"
    "        self._fills[report.key] = report"
)
_GUARD_ANCHOR = "        self._guard_order_consistency(report)\n"
_REPORTED_ANCHOR = (
    "            reported_cumulative=max("
    "(r.cumulative_qty for r in order_fills), default=0),"
)
_NET_ANCHOR = "            net_qty=sum(r.signed_qty for r in fills),"
_STORE_INIT_ANCHOR = (
    "        self._fills: dict[tuple[str, str], ExecutionReport] = {}\n"
)
_APPLIED_ANCHOR = "        self.applied += 1\n"
_CONTRADICTION_ANCHOR = (
    "        if disagreements:\n"
    "            self.contradictions += 1\n"
    "            raise ContradictoryExecution("
)
_KEY_ANCHOR = (
    '        """The `(order_id, exec_id)` §4 deduplicates by. The whole '
    'identity."""\n'
    "        return (self.order_id, self.exec_id)"
)


# --------------------------------------------------------------------------
# NON-VACUITY FIRST — the gate reaches a real ledger and a real stream
# --------------------------------------------------------------------------


def test_the_REAL_TREE_passes_and_the_EVIDENCE_names_what_was_DRIVEN() -> None:
    """The credibility floor: real fills, real duplicates, real reorderings.

    The counts are DERIVED from the gate's own stream constant rather than
    typed, for the reason `test_check_reservation_lifecycle` records: a literal
    here goes stale inside the arc that widens the stream, which is exactly the
    restatement directive 3 forbids.
    """
    unique = {(row[0], row[1]) for row in gate._STREAM}  # pylint: disable=protected-access

    result = _run(REPO)

    assert result.status is Status.PASS, result
    assert f"{len(unique)} unique (order_id, exec_id) fill(s)" in result.evidence, (
        result.evidence
    )
    assert f"{len(unique)} duplicate delivery/deliveries" in result.evidence, (
        result.evidence
    )
    assert "proven-reordered stream(s)" in result.evidence, result.evidence
    assert "UNBOUND" in result.evidence, result.evidence


def test_EVERY_NON_VACUITY_FLOOR_is_a_FLOOR_and_not_TODAYS_COUNT() -> None:
    """Doctrine C.4: a threshold equal to the current number is an anchor that
    moves. Each floor must sit STRICTLY below what the stream carries, so
    widening the stream cannot redden the gate and shrinking it is caught."""
    stream = gate._STREAM  # pylint: disable=protected-access
    unique = {(row[0], row[1]): row for row in stream}

    assert gate.MIN_UNIQUE_FILLS < len(unique)
    assert gate.MIN_ORDERS < len({row[0] for row in unique.values()})
    assert gate.MIN_SYMBOLS < len({row[2] for row in unique.values()})
    assert gate.MIN_SELL_FILLS < len([r for r in unique.values() if r[3] == "sell"])
    assert gate.MIN_DUPLICATE_DELIVERIES < len(unique)
    assert gate.MIN_REORDERED_STREAMS < len(gate._index_orders(len(stream)))  # pylint: disable=protected-access


def test_a_FLOOR_RAISED_ABOVE_THE_STREAM_is_CANNOT_MEASURE_not_a_PASS(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The floor arm must be able to fire, or it is decoration. Raised above the
    real stream, the gate must refuse to report rather than pass."""
    monkeypatch.setattr(gate, "MIN_UNIQUE_FILLS", 999)

    result = _run(REPO)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "below the floor of 999" in result.detail, result.detail
    assert "never deduplicated" in result.detail, result.detail


def test_a_PERMUTATION_THAT_IS_NOT_REORDERED_is_REFUSED_by_the_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§0a's third answer, driven: a 'permutation' equal to the in-order stream
    would agree with anything. The gate must say so rather than count it."""
    monkeypatch.setattr(
        gate,
        "_index_orders",
        lambda size: (tuple(range(size)), tuple(range(size - 1, -1, -1))),
    )

    result = _run(REPO)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "ingest[permutation]" in result.site, result.site
    assert "0 inversion(s) against the floor of" in result.detail, result.detail
    assert "not actually out of order" in result.detail, result.detail


def test_a_DEGENERATE_EXPECTATION_is_REFUSED_before_the_subject_is_consulted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§0a's fifth answer: two symbols sharing a net would hide a ledger reading
    the wrong symbol's fills."""
    monkeypatch.setattr(gate, "_EXPECTED_NET", {"ESZ6": 4, "NQZ6": 4, "RTYZ6": 6})

    result = _run(REPO)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "two symbols share an expected net" in result.detail, result.detail
    assert "wrong symbol's fills would be invisible" in result.detail, result.detail


# --------------------------------------------------------------------------
# PLANT 1 — NO DEDUP. A duplicate delivery enters the SET and double-counts.
# --------------------------------------------------------------------------


def test_a_LEDGER_WITHOUT_DEDUP_fails_and_names_the_POSITION_IT_MOVED(
    home: Path,
) -> None:
    """The store is keyed by a per-delivery counter instead of §4's pair, so a
    re-delivery is a second row. The in-order stream is unaffected — which is
    the whole reason a dedup test built on a clean stream measures nothing."""
    _plant(
        home,
        _DEDUP_ANCHOR,
        "        self._guard_order_consistency(report)\n"
        "        self._fills[(report.order_id, report.exec_id, self.applied)] = report",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "ingest[duplicate]" in result.site, result.site
    assert "delivering every report TWICE changed the derived position" in (
        result.detail
    ), result.detail
    assert "ESZ6=8" in result.detail, result.detail  # 4 doubled
    assert "the duplicates entered the SET" in result.detail, result.detail
    assert "ingest[permutation]" not in result.site, (
        f"a dedup-only plant named the permutation arm too: {result.site}"
    )


# --------------------------------------------------------------------------
# PLANT 2 — OUT-OF-ORDER ARRIVALS DISCARDED as stale. In-order stays correct.
# --------------------------------------------------------------------------


def test_a_LEDGER_THAT_DROPS_STALE_ARRIVALS_fails_only_on_the_REORDERED_stream(
    home: Path,
) -> None:
    """A ledger that assumes the broker's cumulative arrives monotonically and
    discards anything 'stale'. Correct on every in-order stream, wrong the
    moment delivery reorders — the exact defect §4's immunity sentence exists
    to forbid, and one a clean-stream drive cannot see."""
    _plant(
        home,
        _GUARD_ANCHOR,
        _GUARD_ANCHOR + "        _highest = max(\n"
        "            (\n"
        "                r.cumulative_qty\n"
        "                for r in self._fills.values()\n"
        "                if r.order_id == report.order_id\n"
        "            ),\n"
        "            default=0,\n"
        "        )\n"
        "        if report.cumulative_qty < _highest:\n"
        "            self.duplicates += 1\n"
        "            return IngestOutcome(IngestDisposition.DUPLICATE, report)\n",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "ingest[permutation]" in result.site, result.site
    assert "inversion(s)) produced" in result.detail, result.detail
    assert "immunity to out-of-order execution reports" in result.detail, result.detail
    assert "when the broker happened to deliver" in result.detail, result.detail


# --------------------------------------------------------------------------
# PLANT 3 — THE CROSS-CHECK COMPARING A FIGURE WITH ITSELF
# --------------------------------------------------------------------------


def test_an_AUDIT_THAT_READS_ONE_FIELD_TWICE_fails_on_BOTH_the_drive_and_the_source(
    home: Path,
) -> None:
    """§0a's fourth answer. `reported_cumulative` is re-derived from the same
    increments as `derived_cumulative`, so the gap is identically zero over
    every missing execution — the cross-check becomes furniture. Both halves of
    the closure must fire: the behavioural drive and the static field read."""
    _plant(
        home,
        _REPORTED_ANCHOR,
        "            reported_cumulative=sum(r.filled_qty for r in order_fills),",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "audit[withheld]" in result.site, result.site
    assert "audit() reports gap 0" in result.detail, result.detail
    assert "complete=True" in result.detail, result.detail
    assert "read the same field reports 0 over every defect" in result.detail, (
        result.detail
    )
    # The STATIC half of the same closure, on the same plant.
    assert f"{gate.LEDGER}:audit" in result.site, result.site
    assert "never reads cumulative_qty" in result.detail, result.detail


# --------------------------------------------------------------------------
# PLANT 4 — THE ONE NO DRIVE CAN SEE. A correctly-maintained running total.
# --------------------------------------------------------------------------


def _plant_running_total(home: Path) -> None:
    """Position served from a per-symbol total maintained on every APPLIED
    ingest. Correct today, and correct under every stream this gate delivers."""
    _plant(
        home,
        _STORE_INIT_ANCHOR,
        _STORE_INIT_ANCHOR + "        self._net: dict[str, int] = {}\n",
    )
    _plant(
        home,
        _APPLIED_ANCHOR,
        _APPLIED_ANCHOR + "        self._net[report.symbol] = (\n"
        "            self._net.get(report.symbol, 0) + report.signed_qty\n"
        "        )\n",
    )
    _plant(home, _NET_ANCHOR, "            net_qty=self._net.get(symbol, 0),")


def test_a_MAINTAINED_RUNNING_TOTAL_fails_even_though_every_DRIVE_stays_green(
    home: Path,
) -> None:
    """DOCTRINE C.9, ANSWERED BY MEASUREMENT rather than by argument.

    This plant is permutation-invariant, duplicate-immune, reconciles and
    audits. Every behavioural arm of this gate is green over it and so is every
    property `scripts/tests/test_execution.py` owns. ARM STRUCTURE is the only
    instrument in the tree that sees it, which is what makes this gate a
    different instrument rather than a second one.
    """
    _plant_running_total(home)

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert result.site == f"{gate.LEDGER}:position", result.site
    assert "position reads self._net as well as the keyed store self._fills" in (
        result.detail
    ), result.detail
    assert "a maintained running total re-introduces" in result.detail, result.detail
    assert "No drive can see this" in result.detail, result.detail


def test_the_RUNNING_TOTAL_plant_is_INVISIBLE_to_every_BEHAVIOURAL_arm(
    home: Path,
) -> None:
    """The claim above, measured on the SAME plant rather than asserted: the
    planted ledger is driven directly and reproduces the reference position
    under duplication AND under reversal. If this ever stops holding, the plant
    stopped being the defect this argument rests on."""
    _plant_running_total(home)
    loaded, error = gate.load(home)
    assert loaded is not None, error
    stream = gate._STREAM  # pylint: disable=protected-access

    clean = gate._fed(loaded, gate._reports(loaded, stream))  # pylint: disable=protected-access
    doubled = tuple(row for row in stream for _ in range(2))
    dirty = gate._fed(loaded, gate._reports(loaded, doubled))  # pylint: disable=protected-access
    backwards = gate._fed(loaded, gate._reports(loaded, tuple(reversed(stream))))  # pylint: disable=protected-access

    for symbol, expected in gate._EXPECTED_NET.items():  # pylint: disable=protected-access
        assert clean.position(symbol).net_qty == expected, symbol
        assert dirty.position(symbol).net_qty == expected, (
            f"{symbol}: the running-total plant must stay duplicate-immune, or "
            "it is not the defect the C.9 argument rests on"
        )
        assert backwards.position(symbol).net_qty == expected, (
            f"{symbol}: the running-total plant must stay permutation-invariant"
        )


# --------------------------------------------------------------------------
# PLANT 5 — A CONTRADICTORY DUPLICATE ABSORBED as a last-write-wins rewrite
# --------------------------------------------------------------------------


def test_a_SAME_KEY_REWRITE_that_is_ABSORBED_fails_and_names_the_movement(
    home: Path,
) -> None:
    """An exact re-delivery cannot move the position even in a ledger that
    blindly overwrites, so the idempotence arm is blind to this by construction.
    §4 makes a re-delivery idempotent and NOT a rewrite: last-write-wins keeps
    one story about an execution and erases the other."""
    _plant(
        home,
        _CONTRADICTION_ANCHOR,
        "        if disagreements:\n"
        "            self._fills[report.key] = report\n"
        "            return IngestOutcome(IngestDisposition.APPLIED, report)\n"
        "        if disagreements:\n"
        "            self.contradictions += 1\n"
        "            raise ContradictoryExecution(",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "ingest[contradiction]" in result.site, result.site
    assert "was ABSORBED" in result.detail, result.detail
    assert "not a rewrite" in result.detail, result.detail
    assert "no record it existed" in result.detail, result.detail


# --------------------------------------------------------------------------
# PLANT 6 — THE DEDUP KEY COLLAPSED to `exec_id` alone
# --------------------------------------------------------------------------


def test_a_KEY_COLLAPSED_TO_EXEC_ID_fails_and_the_REASON_names_the_collision(
    home: Path,
) -> None:
    """The stream deliberately reuses `a1` under `A-1` and `A-4`. A ledger keyed
    on `exec_id` alone collides two unrelated fills in two different symbols;
    §4's key is the PAIR. The refusal must name what disagreed, never the
    exception type alone (§18)."""
    _plant(home, _KEY_ANCHOR, _KEY_ANCHOR.replace("self.order_id, ", ""))

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "ingest[reference]" in result.site, result.site
    assert "ContradictoryExecution" in result.detail, result.detail
    assert "symbol: 'ESZ6' then 'NQZ6'" in result.detail, result.detail
    assert "a refusal here is the ledger's defect" in result.detail, result.detail


# --------------------------------------------------------------------------
# CANNOT_MEASURE, never PASS — an absent or foreign subject is not agreement
# --------------------------------------------------------------------------


def test_an_ABSENT_LEDGER_is_CANNOT_MEASURE_and_names_the_import_failure(
    home: Path,
) -> None:
    """A gate whose subject is gone measured nothing (§17)."""
    (home / gate.LEDGER).unlink()

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "cannot import nixrisk.execution" in result.detail, result.detail
    assert "never a PASS" in result.detail, result.detail


def test_an_EMPTY_TREE_is_CANNOT_MEASURE_and_names_the_FOREIGN_PATH(
    tmp_path: Path,
) -> None:
    """D3.124, closed here rather than inherited. `checks/_preamble.py` appends
    the REAL `scripts/` to `sys.path` and never removes it, so the import
    against an empty tree does NOT fail — it resolves against this repository.
    Without the `__file__` provenance assertion the gate would PASS while
    measuring the pristine tree and reporting on the empty one."""
    result = _run(tmp_path)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "which is NOT under" in result.detail, result.detail
    assert str(tmp_path) in result.detail, result.detail
    assert "fell through to another tree" in result.detail, result.detail


def test_a_SUBJECT_IMPORTED_FROM_A_DIFFERENT_FILE_UNDER_THE_SAME_ROOT_is_REFUSED(
    home: Path,
) -> None:
    """The provenance rule pins the SUBJECT to one path, not to a root.

    `arm_structure` parses `home/scripts/nixrisk/execution.py` off disk while
    every other arm drives the IMPORTED module. A tree in which the import
    resolves to a DIFFERENT file under the same `scripts/` root would have the
    two halves judging two different files while the root test stayed happy —
    so the gate must refuse rather than average them. The plant is the realistic
    shape rather than a synthetic one: the module grows into a PACKAGE, and a
    regular package wins over a same-named module in the finder's own ordering,
    so `execution.py` stays on disk and stops being what anyone imports.
    """
    package = home / "scripts" / "nixrisk" / "execution"
    package.mkdir()
    shutil.copy(home / gate.LEDGER, package / "__init__.py")

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "not from the scripts/nixrisk/execution.py" in result.detail, result.detail
    assert "judging two different files" in result.detail, result.detail


# --------------------------------------------------------------------------
# THE THIRD STEP — the plants removed, the same population passing
# --------------------------------------------------------------------------


def test_the_SAME_COPIED_TREE_passes_once_every_plant_is_gone(home: Path) -> None:
    """Without this the gate is only known to be able to fail."""
    result = _run(home)

    assert result.status is Status.PASS, result
    assert "proven-reordered stream(s)" in result.evidence, result.evidence


def test_a_PLANT_APPLIED_AND_REVERTED_leaves_the_gate_GREEN_on_the_same_tree(
    home: Path,
) -> None:
    """The control proper: the same tree, red under the plant, green without it,
    with the ledger byte-identical before and after."""
    before = (home / gate.LEDGER).read_bytes()
    _plant_running_total(home)
    planted = _run(home)
    (home / gate.LEDGER).write_bytes(before)
    restored = _run(home)

    assert planted.status is Status.FAIL_NEEDS_OPERATOR, planted
    assert "maintained running total" in planted.detail, planted.detail
    assert restored.status is Status.PASS, restored
    assert (home / gate.LEDGER).read_bytes() == before, "the control was not restored"


def test_the_GATE_LEAVES_THE_INTERPRETER_AS_IT_FOUND_IT(home: Path) -> None:
    """The gate imports a package out of the tree under test. If it left the
    copy resident, the NEXT run in this process would measure the wrong tree —
    which is the whole reason a plant on a copy can be trusted at all."""
    real = sys.modules.get("nixrisk.execution")
    paths_before = list(sys.path)

    _run(home)

    assert sys.path == paths_before, "the gate leaked a sys.path entry"
    assert sys.modules.get("nixrisk.execution") is real, (
        "the gate left the tmp_path copy of nixrisk.execution in sys.modules"
    )


def test_the_GATE_DECLARES_the_ledger_as_a_SUBJECT_so_coverage_is_real() -> None:
    """The coverage ratchet reads SUBJECTS; a gate that measures without
    declaring leaves its artifact looking uncovered, and one that declares
    without measuring is the suppression file the ratchet exists to prevent.
    This is the declaration D3.144 is discharged by."""
    assert gate.LEDGER in gate.SUBJECTS, gate.SUBJECTS
    assert gate.CORRECTABLE is False, "the ledger is never edited into agreement"
    assert gate.NON_CORRECTABLE_REASON, "a refusal must carry its reason"
