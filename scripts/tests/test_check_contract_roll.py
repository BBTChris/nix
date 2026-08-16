"""ARC 033 / Stage 1 / B — the can-fail suite for `checks/check_contract_roll.py`.

Structure follows `nix_check_contract.md` §5.1 / the `check_flatten` precedent:
non-vacuity FIRST (the real tree passes), then plants that must FAIL and NAME
their site, then the plant removed and the same tree passing again.

**No plant touches a production artifact** (doctrine C.8). Every control builds a
throwaway `nix_home` under `tmp_path` holding COPIES of `roll.py`, its seams and
the vendored calendar package, perturbs the COPY, and drives the SHIPPED gate's
own bytes against it. Nothing under `scripts/` is written.

Every control asserts the REASON — the site and the named condition — never the
exit code or the status alone (check contract v2 §11).

THE COST NOTE, because it is why this file is shorter than its sibling: every
control here runs the gate, and the gate runs a threaded race harness twice.
Each plant is therefore chosen to be the CHEAPEST perturbation that isolates one
property, and there are no redundant plants.
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# pylint: disable=missing-function-docstring
# missing-function-docstring: the declaration controls are named after the
# declaration they read; a docstring would restate the name.

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.append(str(REPO / "checks"))

import check_contract_roll as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)

NIXRISK = (
    "scripts/nixrisk/__init__.py",
    "scripts/nixrisk/roll.py",
    "scripts/nixrisk/calendar_seam.py",
    "scripts/nixrisk/seam.py",
)


@pytest.fixture(scope="module")
def _template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """ONE copy of the tree, made once. Copying `calendar_data/` is ~40 MB."""
    root = tmp_path_factory.mktemp("roll_template")
    (root / "scripts" / "nixrisk").mkdir(parents=True)
    for rel in NIXRISK:
        shutil.copy(REPO / rel, root / rel)
    shutil.copytree(REPO / "scripts" / "crucible", root / "scripts" / "crucible")
    return root


@pytest.fixture
def home(_template: Path, tmp_path: Path) -> Path:
    """A throwaway tree per control, cloned from the module-scoped template."""
    target = tmp_path / "home"
    shutil.copytree(_template, target, symlinks=True)
    return target


def _run(nix_home: Path):
    return gate.run(Mode.VERIFY, Context(nix_home=nix_home, mode=Mode.VERIFY))


def _plant(home: Path, old: str, new: str, rel: str = gate.ROLL_FILE) -> None:
    """Rewrite the COPIED source. Fails loudly if the anchor moved."""
    path = home / rel
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"anchor appears {text.count(old)} times, not once"
    path.write_text(text.replace(old, new), encoding="utf-8")


# --------------------------------------------------------------------------
# NON-VACUITY FIRST
# --------------------------------------------------------------------------


def test_the_REAL_TREE_PASSES_and_the_EVIDENCE_states_the_PROVISIONALITY(
    home: Path,
) -> None:
    """A green here must not be readable as "our roll calendar is correct".

    §7.5:520 defines the front month as the volume leader; the vendored artifact
    observes nothing (CHECK-DEBT D3.170). The evidence string has to say so, in
    words, or the instrument misleads the operator reading its one line.
    """
    result = _run(home)

    assert result.status is Status.PASS, result
    assert "ACROSS the roll instant" in result.evidence, result.evidence
    assert "identity SHIFTS, asserted first" in result.evidence, result.evidence
    assert "TWO-STEP plant proven to tear" in result.evidence, result.evidence
    assert "PROVISIONAL" in result.evidence, result.evidence
    assert "RULE-DERIVED" in result.evidence, result.evidence
    assert "high_risk=1" in result.evidence, result.evidence
    assert "D3.170" in result.evidence, result.evidence
    assert "asserts NOTHING about the roll dates being" in result.evidence, (
        result.evidence
    )


def test_the_GATE_DECLARES_its_SUBJECT_so_coverage_is_real() -> None:
    assert gate.ROLL_FILE in gate.SUBJECTS, gate.SUBJECTS
    assert gate.CORRECTABLE is False, "a roll date is never edited into agreement"
    assert gate.NON_CORRECTABLE_REASON, "a refusal must carry its reason"


def test_an_ABSENT_ARTIFACT_is_CANNOT_MEASURE_never_PASS(tmp_path: Path) -> None:
    """§17: a property proven while its subject is unavailable is not proven."""
    result = _run(tmp_path)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "§17" in result.detail, result.detail
    assert "nothing was measured" in result.detail or "OUTSIDE" in result.detail, (
        result.detail
    )


# --------------------------------------------------------------------------
# PLANT 1 — the switch is made NON-ATOMIC
# --------------------------------------------------------------------------


def test_a_NON_ATOMIC_SWITCH_reddens_and_NAMES_the_TORN_SNAPSHOT(home: Path) -> None:
    """THE property. `snapshot()` is rewritten to take N loads instead of one.

    Each `(subsystem, symbol)` pair is then resolved against whatever epoch
    happened to be bound at that moment, so a writer flipping across the roll is
    observable half-applied — the §12.7 torn read, one layer up.
    """
    _plant(
        home,
        "        return self.epoch().snapshot()",
        "        return {\n"
        "            (subsystem, symbol): self.epoch().identities[symbol].contract\n"
        "            for subsystem in self._subsystems\n"
        "            for symbol in self._symbols\n"
        "        }",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "roll.py:atomic" in result.site, result.site
    assert "TORN snapshot" in result.detail, result.detail
    assert "§7.5:522" in result.detail, result.detail


# --------------------------------------------------------------------------
# PLANT 2 — the identity never shifts, so the drive crosses nothing
# --------------------------------------------------------------------------


def test_an_IDENTITY_THAT_NEVER_SHIFTS_reddens_the_NON_VACUITY_arm(
    home: Path,
) -> None:
    """A frozen front month makes every snapshot self-consistent for free.

    This is the vacuous pass the gate exists to refuse: with the identity
    pinned, the race would find no tear and a naive gate would report atomicity
    over a drive that never crossed a roll.
    """
    _plant(
        home,
        "        roll = self._calendar.front_contract(symbol, at)\n"
        "        if roll is None:\n"
        "            return None\n"
        "        return ContractIdentity(\n"
        "            symbol=roll.symbol,\n"
        "            contract=roll.contract,",
        "        roll = self._calendar.front_contract(symbol, at)\n"
        "        if roll is None:\n"
        "            return None\n"
        "        return ContractIdentity(\n"
        "            symbol=roll.symbol,\n"
        "            contract=f'{roll.symbol}PINNED',",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "roll.py:atomic" in result.site, result.site
    assert "did not move across" in result.detail, result.detail
    assert "nothing about atomicity was measured" in result.detail, result.detail


# --------------------------------------------------------------------------
# PLANT 3 — D3.170's provenance is LAUNDERED
# --------------------------------------------------------------------------


def test_a_LAUNDERED_PROVENANCE_reddens_and_NAMES_D3_170(home: Path) -> None:
    """The adapter stops reading `high_risk`, so a rule-derived roll reads clean.

    §7.5:520's front month is the VOLUME LEADER. Converting an honest unknown
    into a false certainty is worse than carrying no flag at all, which is why
    this is a FAIL and not a note.
    """
    _plant(
        home,
        "            if roll is not None and roll.high_risk:",
        "            if False:",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "roll.py:provenance" in result.site, result.site
    assert "D3.170" in result.detail, result.detail
    assert "high_risk=1" in result.detail, result.detail


def test_a_DROPPED_EPOCH_PROVENANCE_reddens_even_when_the_ADAPTER_is_honest(
    home: Path,
) -> None:
    """The flag can also be lost on the way from the adapter to the epoch.

    Two different sites, one property: the consumer must be able to learn the
    provenance of the identity it holds, and it does not matter which hop drops
    it.
    """
    _plant(
        home,
        "            if symbol in self._provisional_source:\n"
        "                provisional.add(symbol)",
        "            if False:\n                provisional.add(symbol)",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "roll.py:provenance" in result.site, result.site
    assert "cannot learn that it is doing so" in result.detail, result.detail


# --------------------------------------------------------------------------
# THE PLANT REMOVED — the same tree passes again
# --------------------------------------------------------------------------


def test_the_SAME_TREE_PASSES_ONCE_the_PLANT_IS_REMOVED(home: Path) -> None:
    """Closes the loop: the reds above are the plant's, not the fixture's."""
    _plant(
        home,
        "            if roll is not None and roll.high_risk:",
        "            if False:",
    )
    assert _run(home).status is Status.FAIL_NEEDS_OPERATOR

    _plant(
        home,
        "            if False:",
        "            if roll is not None and roll.high_risk:",
    )

    assert _run(home).status is Status.PASS
