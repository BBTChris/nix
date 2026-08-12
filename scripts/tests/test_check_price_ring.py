"""ARC 026 C3/C4 — the standing gate over §12.7's SOLE shared-memory exception.

Structure follows `nix_check_contract.md` §5.1: non-vacuity first, then a plant
that must FAIL and NAME its site, then the plant removed and the same population
passing.

**No plant touches a production artifact** (doctrine C.8). The narrowness plants
build a miniature tree under `tmp_path` — a copy of `price_ring.py` at its
allow-listed path so the detector has its known subject, twenty filler modules so
the enumeration is credible, and one stray file that reaches for shared memory.
The real tree is only ever READ, and every `/dev/shm` segment this file creates
carries the test's PID in its name and is unlinked in a `finally`.

**Every control asserts the REASON** — the site or the named condition — never
the exit code alone (check contract v2 §11).
"""
# pylint: disable=invalid-name,redefined-outer-name,import-outside-toplevel
# pylint: disable=protected-access
# `protected-access`: a can-fail control drives the gate's ARMS, which are
# private by design — an arm made public so a test could reach it would be a
# surface the gate did not need, invented for the test. Doctrine C.8 says the
# plant must not touch the production artifact; it does not say the test may
# only use the public API.
# pylint: disable=duplicate-code
# Test names SHOUT the property; fixtures are reused by design; the sys.path
# bootstrap forces late imports. Each deliberate, so the pragma is named.

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
# APPENDED, never inserted at the front — loader.py's failure mode #8 note.
sys.path.append(str(REPO / "checks"))

import check_price_ring as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)
from nixverify.declarations import (  # pylint: disable=wrong-import-position
    read_declaration,
)

GATE_FILE = REPO / "checks" / "check_price_ring.py"
REAL_RING = REPO / "scripts" / "nixbus" / "price_ring.py"

#: The stray. One line, and it is the whole §12.7 violation.
STRAY = "import mmap\n\n\ndef map_something(fd):\n    return mmap.mmap(fd, 0)\n"


def _plant_tree(tmp_path: Path, *, with_ring: bool = True, fillers: int = 25) -> Path:
    """A miniature tree the sweep can walk: filler modules plus the real ring."""
    home = tmp_path / "tree"
    (home / "scripts" / "nixbus").mkdir(parents=True, exist_ok=True)
    for index in range(fillers):
        (home / f"filler_{index}.py").write_text(f"VALUE = {index}\n", encoding="utf-8")
    if with_ring:
        shutil.copy(REAL_RING, home / "scripts" / "nixbus" / "price_ring.py")
    return home


def _run(home: Path):
    """Drive the gate with its sweep pointed at `home`."""
    return gate.run(Mode.VERIFY, Context(nix_home=home, mode=Mode.VERIFY))


# --------------------------------------------------------------------------
# NON-VACUITY FIRST — the ring really carried ticks and the sweep really swept.
# --------------------------------------------------------------------------


def test_the_REAL_tree_PASSES_and_the_evidence_names_what_was_measured() -> None:
    """A green here means ticks moved and the tree was walked, both stated."""
    result = _run(REPO)
    assert result.status is Status.PASS, result.detail
    assert "ring carried 5 real ticks" in result.evidence, result.evidence
    assert "byte-exact" in result.evidence, result.evidence
    assert ".py files swept" in result.evidence, result.evidence


def test_the_segment_is_a_KERNEL_object_present_then_gone() -> None:
    """`/dev/shm` before and after, not a library's report of itself."""
    result = _run(REPO)
    assert "present while alive, absent after close" in result.evidence, result.evidence


def test_the_sweep_DETECTS_every_shared_memory_spelling_it_claims_to(
    tmp_path: Path,
) -> None:
    """A detector is only worth its allow-list if it matches. Four spellings."""
    home = tmp_path / "spellings"
    home.mkdir()
    (home / "a.py").write_text("import mmap\n", encoding="utf-8")
    (home / "b.py").write_text(
        "from multiprocessing import shared_memory\n", encoding="utf-8"
    )
    (home / "c.py").write_text("x = SharedMemory('n')\n", encoding="utf-8")
    (home / "d.py").write_text("P = '/dev/shm/thing'\n", encoding="utf-8")
    (home / "innocent.py").write_text("VALUE = 1\n", encoding="utf-8")
    hits, unparseable, scanned = gate.sweep(home)
    assert not unparseable, unparseable
    assert scanned == 5, scanned
    assert set(hits) == {"a.py", "b.py", "c.py", "d.py"}, sorted(hits)


# --------------------------------------------------------------------------
# PLANT 1 — a SECOND shared-memory user appears in the tree.
# --------------------------------------------------------------------------


def test_a_STRAY_shared_memory_user_fails_and_NAMES_the_file_and_line(
    tmp_path: Path,
) -> None:
    """The headline can-fail: §12.7's exception is SOLE, and this is a second."""
    home = _plant_tree(tmp_path)
    (home / "scripts" / "stray_shm.py").write_text(STRAY, encoding="utf-8")
    result = _run(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.evidence
    assert "scripts/stray_shm.py" in result.site, result.site
    assert "outside §12.7's sole exception" in result.detail, result.detail
    assert "line 1: import mmap" in result.detail, result.detail


def test_UNPLANTING_the_stray_restores_PASS_on_the_same_tree(tmp_path: Path) -> None:
    """The plant removed, the same population passes. Step three of §5.1."""
    home = _plant_tree(tmp_path)
    stray = home / "scripts" / "stray_shm.py"
    stray.write_text(STRAY, encoding="utf-8")
    assert _run(home).status is Status.FAIL_NEEDS_OPERATOR
    stray.unlink()
    restored = _run(home)
    assert restored.status is Status.PASS, restored.detail


# --------------------------------------------------------------------------
# PLANT 2 — the SWEEP ITSELF goes blind. The vacuity that matters.
# --------------------------------------------------------------------------


def test_a_sweep_that_finds_NOTHING_ANYWHERE_is_CANNOT_MEASURE_not_PASS(
    tmp_path: Path,
) -> None:
    """Zero hits means the detector is broken, not that the tree is clean."""
    result = _run(_plant_tree(tmp_path, with_ring=False))
    assert result.status is Status.CANNOT_MEASURE, result.status
    assert "the detector is broken" in result.detail, result.detail
    assert "artefact of the instrument" in result.detail, result.detail


def test_a_sweep_over_TOO_FEW_FILES_is_CANNOT_MEASURE_and_names_the_floor(
    tmp_path: Path,
) -> None:
    """An enumeration that cannot be right does not get to report a clean tree."""
    result = _run(_plant_tree(tmp_path, fillers=2))
    assert result.status is Status.CANNOT_MEASURE
    assert str(gate.MIN_CREDIBLE_FILES) in result.detail, result.detail


def test_a_file_that_WILL_NOT_PARSE_is_CANNOT_MEASURE_not_a_skip(
    tmp_path: Path,
) -> None:
    """A skipped file could be exactly the one mapping shared memory."""
    home = _plant_tree(tmp_path)
    (home / "broken.py").write_text("def (\n", encoding="utf-8")
    result = _run(home)
    assert result.status is Status.CANNOT_MEASURE
    assert "did not cover the tree" in result.detail, result.detail


# --------------------------------------------------------------------------
# PLANT 3 — the ring stops counting its own gap.
# --------------------------------------------------------------------------


def test_an_overrun_that_MISCOUNTS_fails_and_NAMES_the_resync_site(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ring that drops silently is worse on the hot path than one that fails."""
    monkeypatch.setattr(gate, "_overrun", lambda _name: (8, 0))
    result = _run(_plant_tree(tmp_path))
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.evidence
    assert "price_ring.py:PriceRingReader._resync" in result.site, result.site
    assert "arithmetic answer" in result.detail, result.detail


def test_UNPLANTING_the_miscount_restores_PASS(tmp_path: Path) -> None:
    """Step three of §5.1 for plant 3 — the real `_overrun` counts exactly."""
    result = _run(_plant_tree(tmp_path))
    assert result.status is Status.PASS, result.detail
    assert "overrun counted exactly: 8 recovered, 12 dropped" in result.evidence


# --------------------------------------------------------------------------
# PLANT 4 — "strictly one writer by construction" becomes a convention.
# --------------------------------------------------------------------------


def test_a_SECOND_WRITER_being_allowed_fails_and_NAMES_the_claim_site(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§12.7's single-writer guarantee, planted away and caught."""
    monkeypatch.setattr(gate, "_second_writer_refusal", lambda _name: "")
    result = _run(_plant_tree(tmp_path))
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.evidence
    assert "price_ring.py:PriceRingWriter._claim_segment" in result.site, result.site
    assert "not a construction" in result.detail, result.detail


def test_a_refusal_that_NAMES_NO_PID_is_itself_a_defect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refusal naming nothing is indistinguishable from any other open failure."""
    monkeypatch.setattr(gate, "_second_writer_refusal", lambda _name: "refused")
    result = _run(_plant_tree(tmp_path))
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "does not name the incumbent PID" in result.detail, result.detail


# --------------------------------------------------------------------------
# PLANT 5 — ticks arrive with the wrong content, or do not arrive at all.
# --------------------------------------------------------------------------


def test_a_tick_that_comes_back_CHANGED_fails_and_NAMES_the_poll_site(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Counting ticks is not checking them."""
    real = gate._round_trip

    def _corrupt(name: str):
        drive = real(name)
        drive.ticks[0] = drive.ticks[0].__class__(
            symbol_id=drive.ticks[0].symbol_id,
            price=0.0,
            size=drive.ticks[0].size,
            venue_ts_ns=drive.ticks[0].venue_ts_ns,
            seq=drive.ticks[0].seq,
        )
        return drive

    monkeypatch.setattr(gate, "_round_trip", _corrupt)
    result = _run(_plant_tree(tmp_path))
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.evidence
    assert "price_ring.py:PriceRingReader.poll" in result.site, result.site
    assert "came back as" in result.detail, result.detail


def test_a_ring_that_carried_NO_TICKS_is_CANNOT_MEASURE_not_PASS(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The transport-vacuity rule, applied to the firehose."""
    real = gate._round_trip

    def _empty(name: str):
        drive = real(name)
        drive.ticks = []
        return drive

    monkeypatch.setattr(gate, "_round_trip", _empty)
    result = _run(_plant_tree(tmp_path))
    assert result.status is Status.CANNOT_MEASURE, result.status
    assert "ZERO were recovered" in result.detail, result.detail


# --------------------------------------------------------------------------
# Declarations and the actuation surface.
# --------------------------------------------------------------------------


def test_declarations_are_readable_STATICALLY_without_importing_the_check() -> None:
    """§3.3: `--optimize` must read these without executing the measurement."""
    declaration = read_declaration(GATE_FILE)
    assert not declaration.errors, declaration.errors
    assert not declaration.depends_on
    assert declaration.resources == ("shm",)
    assert declaration.subjects == (
        "scripts/nixbus/price_ring.py",
        "scripts/nixbus/__init__.py",
    )


def test_the_gate_REFUSES_actuation_and_says_why() -> None:
    """A flagless check never mutates, and `--correct` is refused with a reason."""
    proc = subprocess.run(  # nosec B603 - fixed argv, shell=False
        [sys.executable, str(GATE_FILE), "--correct"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    combined = proc.stdout + proc.stderr
    assert "manufacturing its own green" in combined, combined


def test_the_ALLOW_LIST_is_four_entries_and_names_them() -> None:
    """An allow-list that grew quietly would be the exception widening quietly."""
    assert gate.ALLOWED == frozenset(
        {
            "scripts/nixbus/price_ring.py",
            "checks/check_price_ring.py",
            "scripts/tests/test_price_ring.py",
            "scripts/tests/test_check_price_ring.py",
        }
    ), sorted(gate.ALLOWED)


def test_a_DOCSTRING_mentioning_shared_memory_is_NOT_a_use(tmp_path: Path) -> None:
    """The false-positive class that would have made this detector unusable.

    Every file in this tree that explains why it does not touch shared memory
    contains the words. A detector that flagged prose would concentrate its false
    positives on exactly the files discussing the rule.
    """
    home = tmp_path / "prose"
    home.mkdir()
    (home / "talks.py").write_text(
        '"""This module never uses /dev/shm or SharedMemory."""\n\nVALUE = 1\n',
        encoding="utf-8",
    )
    (home / "uses.py").write_text("P = '/dev/shm/real'\n", encoding="utf-8")
    hits, _unparseable, _scanned = gate.sweep(home)
    assert set(hits) == {"uses.py"}, sorted(hits)
