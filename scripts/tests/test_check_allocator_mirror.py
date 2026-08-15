"""ARC 031 / Stage 1 A — the CAN-FAIL suite for `checks/check_allocator_mirror.py`.

Doctrine C.2: *a gate is guilty until shown able to say no.* This file is that
demonstration, and it is the §0e artifact — a committed, runnable control that
drives the SHIPPED gate's own bytes RED.

**Non-vacuity first** (the real tree and an untouched copy both PASS), then one
plant per property the gate claims to measure, each required to redden AND to
NAME its site, then the plant removed and the same tree green again.

**No plant touches a production artifact** (doctrine C.8). Every control builds a
throwaway `nix_home` under `tmp_path` holding COPIES of `nixalloc/mirror.py`,
`nixalloc/seam.py`, `nixrisk/seam.py`, `nixrisk/picture.py`, `nixbus/statebus.py`
and their `__init__.py` files, perturbs a COPY, and points the gate at it. The
last test asserts the real `scripts/nixalloc/mirror.py` is byte-identical to the
restored copy, so a plant that leaked would be caught here rather than in review.

Every control asserts the REASON — the site and the named condition — never the
exit code or the status alone (check contract v2 §11).
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.append(str(REPO / "checks"))

import check_allocator_mirror as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)

SUBJECT = "scripts/nixalloc/mirror.py"
COPIED = (
    SUBJECT,
    "scripts/nixalloc/seam.py",
    "scripts/nixalloc/__init__.py",
    "scripts/nixrisk/seam.py",
    "scripts/nixrisk/picture.py",
    "scripts/nixrisk/__init__.py",
    "scripts/nixbus/statebus.py",
    "scripts/nixbus/__init__.py",
)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """A throwaway tree carrying COPIES of the subject and everything it imports."""
    for rel in COPIED:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / rel, target)
    return tmp_path


def _run(nix_home: Path):
    return gate.run(Mode.VERIFY, Context(nix_home=nix_home, mode=Mode.VERIFY))


def _plant(home: Path, old: str, new: str, rel: str = SUBJECT) -> None:
    """Rewrite a COPIED file. Fails loudly if the anchor moved or is ambiguous."""
    path = home / rel
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, (
        f"{rel}: anchor appears {text.count(old)} times, not once — the plant "
        "would measure something other than what it names"
    )
    path.write_text(text.replace(old, new), encoding="utf-8")


def _red(result, *, site_contains: str, why_contains: str) -> None:
    assert result.status is Status.FAIL_NEEDS_OPERATOR, (
        f"expected FAIL_NEEDS_OPERATOR, got {result.status!r}: {result.detail}"
    )
    assert site_contains in (result.site or ""), (
        f"site {result.site!r} does not name {site_contains!r}"
    )
    assert why_contains in (result.detail or ""), (
        f"detail does not name {why_contains!r}: {result.detail}"
    )


# --------------------------------------------------------------------------
# NON-VACUITY FIRST
# --------------------------------------------------------------------------


def test_the_REAL_tree_passes_and_says_what_it_measured() -> None:
    """A gate that cannot pass on a clean subject measures nothing on a dirty one."""
    result = _run(REPO)
    assert result.status is Status.PASS, result.detail
    for marker in ("A1:", "A2:", "A3:", "A4:", "REAL wire"):
        assert marker in (result.evidence or ""), (
            f"the PASS does not report {marker!r}: {result.evidence}"
        )
    assert "0 torn" in (result.evidence or ""), result.evidence
    assert "falsifier caught" in (result.evidence or ""), result.evidence


def test_an_untouched_COPY_also_passes(home: Path) -> None:
    """Every plant below is measured against THIS baseline, not against the repo."""
    assert _run(home).status is Status.PASS


def test_the_gate_DECLARES_the_mirror_as_its_subject_and_refuses_to_correct() -> None:
    """Coverage is what SUBJECTS names; the ratchet can see nothing else."""
    assert gate.SUBJECTS == (SUBJECT,)
    assert gate.CORRECTABLE is False
    assert "authority violation" in gate.NON_CORRECTABLE_REASON
    assert "zmq-ipc" in gate.RESOURCES
    assert "file-write:/tmp" in gate.RESOURCES


def test_a_MISSING_subject_is_cannot_measure_never_a_PASS(tmp_path: Path) -> None:
    """§17: a property proven while its subject is unavailable is not proven."""
    result = _run(tmp_path)
    assert result.status is Status.CANNOT_MEASURE, result
    assert "never a PASS" in (result.detail or ""), result.detail
    assert SUBJECT in (result.detail or ""), result.detail
    # THE MEASURED DEFECT (ARC 031): the first draft of this gate PASSED here,
    # because `_preamble` leaves the real scripts/ on sys.path forever and the
    # import fell through to the live repository. The provenance assertion is
    # what makes an empty tree unmeasurable instead of pristine.
    assert "is NOT under" in (result.detail or ""), result.detail


def test_the_gate_reads_the_tree_it_was_GIVEN_not_the_live_repo(home: Path) -> None:
    """`_preamble` appends the REAL scripts/ to sys.path forever.

    A name-based import would resolve `nixalloc.mirror` against the live
    repository and every plant below would be measuring the pristine tree.
    """
    _plant(home, "an UNSTAMPED ", "an PLANTED-MARKER-9f3a ")
    result = _run(home)
    assert "PLANTED-MARKER-9f3a" in (result.detail or ""), (
        f"the gate reported the live tree's mirror, not the copy's: {result}"
    )


# --------------------------------------------------------------------------
# A1 — ATOMICITY
# --------------------------------------------------------------------------


def test_a_HALF_APPLIED_store_reddens_the_atomicity_arm(home: Path) -> None:
    """The plant publishes an intermediate picture the reader can catch."""
    _plant(
        home,
        """        self._cell = _Cell(
            picture=picture,
            stamps=MappingProxyType(merged),
            heard=True,
            reason="",
        )""",
        """        half = dataclasses.replace(picture, positions=(), sum_open_margin=0.0)
        self._cell = _Cell(
            picture=half,
            stamps=MappingProxyType(merged),
            heard=True,
            reason="",
        )
        time.sleep(0.0002)
        self._cell = _Cell(
            picture=picture,
            stamps=MappingProxyType(merged),
            heard=True,
            reason="",
        )""",
    )
    result = _run(home)
    _red(
        result,
        site_contains="AllocatorMirror.snapshot[atomicity]",
        why_contains="TORN snapshot",
    )


# --------------------------------------------------------------------------
# A2 — THE HALF-BUILT MIRROR RULE
# --------------------------------------------------------------------------


def test_ACCEPTING_an_unstamped_snapshot_reddens_the_staleness_arm(
    home: Path,
) -> None:
    """§12.7: *never sizes on a half-built mirror*."""
    _plant(home, "if picture.version <= 0:", "if picture.version <= -99:")
    result = _run(home)
    _red(
        result,
        site_contains="snapshot[staleness]",
        why_contains="an unstamped snapshot was refused without naming the stamp",
    )


def test_DELETING_the_half_built_rule_ENTIRELY_reddens_the_staleness_arm(
    home: Path,
) -> None:
    """The stronger plant: the mirror HOLDS the unstamped snapshot and sizes on it.

    Deleting only the `version <= 0` line leaves `picture_defects` catching the
    same case for a different reason, which is defence in depth and is why the
    plant above reddens on the REASON rather than on the state. This plant
    removes the whole rule, so the mirror really does report FRESH.
    """
    _plant(
        home,
        "        if _writable(picture.positions):",
        "        if picture is not None:\n"
        '            return ""  # planted: the half-built rule deleted\n'
        "        if _writable(picture.positions):",
    )
    result = _run(home)
    _red(
        result,
        site_contains="snapshot[staleness]",
        why_contains="unstamped snapshot: state is",
    )


def test_COLLAPSING_partial_into_empty_reddens_the_staleness_arm(home: Path) -> None:
    """ARC 027's hazard: a missed snapshot must not look like a quiet feed."""
    _plant(
        home,
        '        self._refuse(f"{_SITE}: {note}", heard=update.heard)',
        '        self._refuse(f"{_SITE}: {note}", heard=False)',
    )
    result = _run(home)
    _red(
        result,
        site_contains="snapshot[staleness]",
        why_contains="heard but no snapshot yet: state is",
    )


def test_a_mirror_that_never_goes_STALE_reddens(home: Path) -> None:
    """§6.4: the rule for a stale cache is refuse, never carry on with the value."""
    _plant(home, "        if age > self._max_age_s:", "        if age > 1e18:")
    result = _run(home)
    _red(
        result,
        site_contains="snapshot[staleness]",
        why_contains="quiet past the ceiling: state is",
    )


# --------------------------------------------------------------------------
# A3 — MONOTONIC-BY-SOURCE, PER KEY
# --------------------------------------------------------------------------


def test_DELETING_the_per_key_guard_reddens_and_names_the_key(home: Path) -> None:
    """§6.4b: *a late update on one key can never regress another*."""
    _plant(
        home,
        "            if incoming is not None and incoming < held_stamp:",
        "            if incoming is not None and incoming < -1.0e18:",
    )
    result = _run(home)
    _red(
        result,
        site_contains="_regression[monotonic-by-source]",
        why_contains="step 1: a reading whose margin:ES stamp is OLDER",
    )
    assert "regressed a held value" in (result.detail or ""), result.detail


def test_DELETING_the_version_tier_reddens_the_monotonic_arm(home: Path) -> None:
    """The transport-order tier is a separate property from the venue-order one."""
    _plant(
        home,
        "        if picture.version <= held.version:",
        "        if picture.version <= -1:",
    )
    result = _run(home)
    _red(
        result,
        site_contains="_regression[monotonic-by-source]",
        why_contains="OLDER picture version was not discarded",
    )


def test_a_guard_that_DISCARDS_EVERYTHING_reddens_too(home: Path) -> None:
    """A gate that only proves refusals would pass a mirror that never updates."""
    _plant(
        home,
        '        held = self._cell.picture\n        if held is None:\n            return ""',
        '        held = self._cell.picture\n        if held is None:\n            return ""\n'
        '        return "planted: everything is a regression"',
    )
    result = _run(home)
    _red(
        result,
        site_contains="_regression[monotonic-by-source]",
        why_contains="was not applied",
    )


def test_a_SILENT_discard_reddens_even_when_the_value_is_right(home: Path) -> None:
    """`discarded_older` is the only external evidence that the guard ever fired."""
    _plant(
        home,
        "            self.discarded_older += 1\n            self._refuse(regression, heard=True)",
        "            self._refuse(regression, heard=True)",
    )
    result = _run(home)
    _red(
        result,
        site_contains="_regression[monotonic-by-source]",
        why_contains="discarded_older did not increment",
    )


# --------------------------------------------------------------------------
# A4 — READ-ONLY
# --------------------------------------------------------------------------


def test_HOLDING_a_writable_picture_reddens_the_read_only_arm(home: Path) -> None:
    """A mirror the Allocator can write is a canonical-state write with no event."""
    _plant(
        home,
        '    return hasattr(type(container), "__setitem__")',
        "    return False  # planted",
    )
    result = _run(home)
    _red(
        result,
        site_contains="AllocatorMirror[read-only]",
        why_contains="WRITABLE margin mapping was held",
    )


def test_a_PUBLIC_VERB_that_accepts_a_picture_reddens(home: Path) -> None:
    """§2: nothing may install a picture the Limiter never sent."""
    _plant(
        home,
        "    def version(self) -> int:",
        "    def install(self, picture: FinancialPicture) -> None:\n"
        '        """Planted mutating verb."""\n'
        '        self._cell = _Cell(picture, MappingProxyType({}), True, "")\n\n'
        "    def version(self) -> int:",
    )
    result = _run(home)
    _red(
        result,
        site_contains="AllocatorMirror[read-only]",
        why_contains="accept a financial picture",
    )
    assert "install(picture)" in (result.detail or ""), result.detail


# --------------------------------------------------------------------------
# THE REAL TRANSPORT
# --------------------------------------------------------------------------


def test_a_DELTA_ONLY_mirror_treated_as_COMPLETE_reddens_the_transport_arm(
    home: Path,
) -> None:
    """§12.7: a delta alone never completes a mirror; only a snapshot does."""
    _plant(home, "        if not mirror.complete:", "        if not mirror.applied:")
    result = _run(home)
    _red(
        result,
        site_contains="StateBusFeed[ipc]",
        why_contains="fed ONLY deltas reports",
    )


# --------------------------------------------------------------------------
# RESTORE
# --------------------------------------------------------------------------


def test_the_plant_REMOVED_returns_the_same_tree_to_green(home: Path) -> None:
    """A red that does not clear on repair is a broken gate, not a finding."""
    original = (home / SUBJECT).read_text(encoding="utf-8")
    _plant(home, "if picture.version <= 0:", "if picture.version <= -99:")
    assert _run(home).status is Status.FAIL_NEEDS_OPERATOR
    (home / SUBJECT).write_text(original, encoding="utf-8")
    restored = _run(home)
    assert restored.status is Status.PASS, restored.detail
    assert (home / SUBJECT).read_bytes() == (REPO / SUBJECT).read_bytes(), (
        "the restored copy differs from the shipped artifact — a plant leaked"
    )
