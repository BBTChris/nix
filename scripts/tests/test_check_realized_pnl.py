"""ARC 037 / sub-agent A — the can-fail suite for `checks/check_realized_pnl.py`.

Structure follows `nix_check_contract.md` §5.1 and the `check_flatten` /
`check_scoring_ema` precedent: **non-vacuity first** (the shipped tree produces
no finding), then one control per plant that must produce a finding NAMING its
site and its reason, then the plant reverted and the same arms green again.

**No plant touches a production artifact** (doctrine C.8). Every control asks
the gate's own `plant_tree` for a throwaway COPY of `scripts/nixrisk` and
`scripts/nixscore` under `tmp_path`, mutates the COPY, and drives the SHIPPED
gate's own bytes against it. `scripts/nixrisk/realized.py` and
`scripts/nixrisk/flatten.py` are read and never written here.

Every control asserts the REASON — the site and the named condition — never a
status or an exit code alone (check contract v2 §11).

§7.12 — what would make THIS suite pass while measuring nothing?

* **A plant could fail to apply** and leave a pristine subject, so the arm's
  silence would be read as proof it can fail. *Closed:* `plant_tree` raises
  `PlantFailed` on an anchor that is not present exactly once, and one control
  drives a deliberately-wrong anchor to prove that refusal is real.
* **The arms could be driven on the shipped tree in every control**, which is
  the same defect one level up. *Closed:* every plant control asserts the arm is
  GREEN on the clean tree first (the non-vacuity test) and RED on the planted
  one, so the difference is the measurement.
* **The Postgres arm is NOT driven here** and that is stated rather than
  implied: it needs a live cluster, and a suite that skipped on its absence
  would report a green that means "not run". It is driven by the gate itself
  (`./.venv/bin/python checks/check_realized_pnl.py`), whose verdict carries the
  figures it read back by SQL.
"""

# pylint: disable=invalid-name,redefined-outer-name,protected-access
# pylint: disable=duplicate-code,wrong-import-position,missing-function-docstring
# import-outside-toplevel: `standalone_main` is imported at the call site the
# same way every check's `__main__` block imports it — at module scope it would
# be a second import path for the actuation surface this suite is measuring.
# pylint: disable=import-outside-toplevel

from __future__ import annotations

import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.append(str(REPO / "checks"))

import check_realized_pnl as gate
from nixverify.contract import Context, Mode, Status
from nixverify.declarations import read_declaration

GATE_FILE = REPO / "checks" / "check_realized_pnl.py"


@pytest.fixture(scope="module")
def clean():
    """The subject, imported from the REAL tree. Read-only in this suite."""
    return gate.load(REPO)


def _plant(tmp_path: Path, label: str):
    """The gate's own plant machinery, for the named plant."""
    edits = dict(gate.PLANTS)[label]
    return gate.load(gate.plant_tree(REPO, tmp_path, edits))


def _sites(findings) -> set[str]:
    return {finding.site for finding in findings}


def _why(findings) -> str:
    return " || ".join(finding.why for finding in findings)


# --------------------------------------------------------------------------
# NON-VACUITY FIRST — the shipped tree passes every in-process arm
# --------------------------------------------------------------------------


def test_the_SHIPPED_TREE_produces_NO_finding_from_any_in_process_arm(clean) -> None:
    """If this ever fails, every red below is meaningless: the controls would be
    measuring a tree that was already broken."""
    assert not gate.peak_defects(clean)
    assert not gate.once_defects(clean)
    assert not gate.constant_defects(clean)
    assert not gate.attribution_defects(clean)
    assert not gate._missing_on_written_rows(clean)
    assert not gate._banned_on_written_rows(clean)


def test_the_SHIPPED_WRITER_actually_writes_a_FIGURE_the_arms_could_judge(
    clean,
) -> None:
    """The floor under the test above: arms that found nothing because there was
    nothing to find would also return `[]`."""
    rows = gate._written_payloads(clean)
    carried = [row for row in rows if clean.realized.REALIZED_FIELD in row["payload"]]
    assert len(carried) == 1, rows
    assert float(carried[0]["payload"][clean.realized.REALIZED_FIELD]) == pytest.approx(
        -103.88
    )
    assert carried[0]["strategy_id"] == gate.STRATEGY
    assert carried[0]["payload"][clean.realized.SYMBOL_FIELD] == gate.SYMBOL


# --------------------------------------------------------------------------
# THE PLANTS — each must be CAUGHT and must NAME what it did
# --------------------------------------------------------------------------


def test_a_PEAK_PRICED_WRITER_is_CAUGHT_and_NAMES_the_open_mark(tmp_path: Path) -> None:
    """§6.6:435. The trade goes +$146 green while open and closes -$104 red."""
    findings = gate.peak_defects(_plant(tmp_path, "peak-priced-writer"))
    assert findings, "the peak plant was not caught"
    assert _sites(findings) == {f"{gate.REALIZED_FILE}:realized_pnl"}
    why = _why(findings)
    assert "146.12" in why and "-103.88" in why
    assert "PEAKED at 5015.0" in why
    assert "never steer capital" in why


def test_a_DOUBLE_COUNTING_WRITER_is_CAUGHT_and_NAMES_THE_SUM(tmp_path: Path) -> None:
    """Two realizing rows for one close double the trade's contribution to
    §6.6:438's per-day sum. The finding must carry the DOUBLED number, not just
    a row count — a count could be a reporting artefact; the sum is the harm."""
    findings = gate.once_defects(_plant(tmp_path, "double-counting-writer"))
    assert findings, "the double-count plant was not caught"
    assert f"{gate.FLATTEN_FILE}:_realized_booked" in _sites(findings)
    why = _why(findings)
    assert "-207.76" in why, why
    assert "SUMMING its realizations" in why
    assert "§12.1 replay" in why, "the ordering that can express the defect"


def test_a_BANNED_FIELD_WRITER_is_CAUGHT_and_NAMES_THE_FIELD(tmp_path: Path) -> None:
    """A payload carrying a realization AND a mark is one field name away from
    steering capital on the wrong one."""
    findings = gate._banned_on_written_rows(_plant(tmp_path, "banned-field-writer"))
    assert findings, "the banned-field plant was not caught"
    assert f"{gate.FLATTEN_FILE}:_realizing_fields" in _sites(findings)
    assert "unrealized_pnl" in _why(findings)


def test_a_FIGURE_STRIPPED_WRITER_is_CAUGHT_and_NAMES_THE_KEY(tmp_path: Path) -> None:
    """D3.220 itself, re-created: the realizing row lands with no figure."""
    findings = gate._missing_on_written_rows(_plant(tmp_path, "figure-stripped-writer"))
    assert findings, "the stripped-figure plant was not caught"
    assert f"{gate.FLATTEN_FILE}:_book" in _sites(findings)
    why = _why(findings)
    assert "realized_pnl" in why
    assert "cold start" in why


def test_the_STRIPPED_ROW_is_ALSO_refused_BY_THE_SCORER_BY_NAME(clean) -> None:
    """The other half of door 3: the reader is reading THIS key. Driven on the
    row the SHIPPED writer produced, with the key removed."""
    rows = gate._written_payloads(clean)
    carried = next(
        row for row in rows if clean.realized.REALIZED_FIELD in row["payload"]
    )
    stripped = dict(carried)
    stripped["payload"] = {
        key: value
        for key, value in carried["payload"].items()
        if key != clean.realized.REALIZED_FIELD
    }
    with pytest.raises(clean.ema.MissingRealized) as caught:
        clean.ema.realized_closes([stripped])
    assert clean.realized.REALIZED_FIELD in str(caught.value)


# --------------------------------------------------------------------------
# THE PLANT MACHINERY ITSELF
# --------------------------------------------------------------------------


def test_a_MISSING_ANCHOR_is_a_LOUD_BLIND_CONTROL_not_a_quiet_green(
    tmp_path: Path,
) -> None:
    """A `str.replace` that matched nothing leaves a PRISTINE subject, the arm
    finds no defect, and the arm's silence is then read as proof it can fail."""
    with pytest.raises(gate.PlantFailed) as caught:
        gate.plant_tree(
            REPO,
            tmp_path,
            ((gate.FLATTEN_FILE, "this anchor is not in the file", "x"),),
        )
    assert "appears 0 time(s)" in str(caught.value)
    assert "measuring nothing" in str(caught.value)


def test_a_PLANT_APPLIED_AND_REVERTED_leaves_the_ARMS_GREEN(tmp_path: Path) -> None:
    """The suite's own both-halves control: the reds above are the PLANT's and
    not an artefact of driving the subject out of a copied tree."""
    planted = _plant(tmp_path, "peak-priced-writer")
    assert gate.peak_defects(planted), "the plant did not take"
    pristine = gate.load(gate.plant_tree(REPO, tmp_path, ()))
    assert not gate.peak_defects(pristine)
    assert not gate.once_defects(pristine)


def test_EVERY_DECLARED_PLANT_IS_DRIVEN_by_the_gate_s_own_control_loop() -> None:
    """`controls()` walks `PLANTS`; a plant added without a `_planted_defects`
    branch would fall through to the last one and be driven twice while another
    is never driven at all."""
    assert len(gate.PLANTS) == 4
    labels = [label for label, _ in gate.PLANTS]
    assert labels == [
        "peak-priced-writer",
        "double-counting-writer",
        "banned-field-writer",
        "figure-stripped-writer",
    ]


# --------------------------------------------------------------------------
# §17 — AN UNAVAILABLE SUBJECT IS CANNOT_MEASURE, NEVER A PASS
# --------------------------------------------------------------------------


def test_an_UNIMPORTABLE_SUBJECT_is_CANNOT_MEASURE_and_NAMES_the_tree(
    tmp_path: Path,
) -> None:
    """§17: a property proven while its subject is unavailable is not proven."""
    result = gate.run(Mode.VERIFY, Context(nix_home=tmp_path, mode=Mode.VERIFY))
    assert result.status is Status.CANNOT_MEASURE, result
    assert str(tmp_path) in result.detail
    assert "never a PASS" in result.detail
    # And the reason is the RIGHT one: an empty home does not fail to import,
    # it imports the REAL tree off a `sys.path` that already carried it, which
    # would make every arm below measure a subject the caller did not name.
    assert "RESOLVED OUTSIDE IT" in result.detail, result.detail
    assert "nixrisk.realized" in result.detail


# --------------------------------------------------------------------------
# THE CONTRACT SURFACE — declarations read STATICALLY, mutation refused
# --------------------------------------------------------------------------


def test_the_DECLARATIONS_are_readable_WITHOUT_IMPORTING_the_check() -> None:
    """Check contract §4.4: `verify.py` reads these by AST and never imports."""
    declaration = read_declaration(GATE_FILE)
    assert not declaration.errors, declaration.errors
    assert declaration.depends_on == ("check_plane1_schema",)
    assert "subprocess:psql" in declaration.resources
    assert "file-write:/tmp" in declaration.resources
    assert declaration.on_fail == "continue"
    assert declaration.correctable is False
    assert declaration.non_correctable_reason.strip()
    assert declaration.subjects == ("scripts/nixrisk/realized.py",)


def test_the_CLI_DEFAULT_IS_MEASURE_ONLY_and_a_MUTATION_IS_REFUSED(
    capsys, tmp_path: Path
) -> None:
    """Contract rule 1: default = measure-only; a flagless check never mutates.
    Rule §2.3: a check that refuses correction says WHY, on its own CLI."""
    from nixverify.actuation import standalone_main

    code = standalone_main(
        GATE_FILE, gate.run, gate.NAME, argv=[str(tmp_path), "--correct"]
    )
    assert code == 1
    refusal = capsys.readouterr().err
    assert "REFUSED" in refusal
    assert "money figure MEANS" in refusal, refusal

    # And the flagless invocation measures rather than mutates: over an empty
    # home it can only report that it could not look (exit 2).
    code = standalone_main(GATE_FILE, gate.run, gate.NAME, argv=[str(tmp_path)])
    assert code == 2, capsys.readouterr()
