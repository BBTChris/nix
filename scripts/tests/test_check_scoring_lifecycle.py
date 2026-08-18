"""The score-lifecycle gate must REDDEN on every way §6.6's two locked
properties can be broken — measured by breaking a REAL COPY of the shipped store
and running the SHIPPED gate against the broken tree.

§6.6:429-433 makes one claim in two halves: the pair-keyed row *"persists across
process death"* and quarantine *"removes exactly that strategy's rows (archived,
not destroyed)"*. Each half below is broken on its own, in a throwaway tree, and
the gate must name the reason — never merely exit non-zero (check contract §18).

Doctrine C.8: no plant touches a production artefact. Every broken store is
written under `tmp_path`, and the gate is pointed at that home.

## §0a on this file: what would make it pass while measuring nothing?

Four answers, and each is an arm here rather than a note:

  * **The gate could red on everything, including the honest store.** So every
    plant is a PAIR — the same tree, the same gate, one edit apart — and the
    unbroken half is asserted GREEN first, in `test_the_gate_PASSES...`.
  * **The gate could red for the wrong reason.** Exit codes are a shared
    namespace: an import error, a missing interpreter and a torn store all reach
    FAIL. Every arm therefore asserts on the DETAIL text naming the property,
    not on the status alone.
  * **A plant could be a no-op.** `_break` asserts its anchor exists and that the
    text actually changed, so a plant that silently missed is a test error rather
    than a green.
  * **The atomicity plant could red for a reason unrelated to tearing.** It
    asserts the detail names an unreadable store left by a KILLED victim, which
    is the torn-document sentence and nothing else.
"""

# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# pylint: disable=missing-function-docstring
# Test names spell the OUTCOME. The sys.path bootstrap is repeated per module
# deliberately; one shared helper would let a single edit un-bind several.
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parents[2]
for _extra in (str(REPO / "checks"), str(REPO / "scripts")):
    if _extra not in sys.path:
        sys.path.insert(0, _extra)

# pylint: disable=wrong-import-position
import check_scoring_lifecycle as gate  # pylint: disable=import-error
from nixverify.contract import Context, Mode, Status  # pylint: disable=import-error

STORE_MODULE = "scripts/nixscore/store.py"


# ---------------------------------------------------------------------------
# A throwaway home holding a REAL copy of the store the gate can be pointed at
# ---------------------------------------------------------------------------


@pytest.fixture()
def home(tmp_path: Path) -> Path:
    """A tree with `scripts/nixscore/` and `scripts/nixbus/` copied in.

    The gate spawns children with this home's `scripts/` on `PYTHONPATH`, so a
    broken copy here is genuinely the subject under test — not a monkeypatched
    attribute in this interpreter, which would prove the gate reads a name
    rather than a tree, and which the children could not see anyway.
    """
    dst = tmp_path / "nix"
    (dst / "scripts").mkdir(parents=True)
    ignore = shutil.ignore_patterns("__pycache__")
    shutil.copytree(
        REPO / "scripts" / "nixscore", dst / "scripts" / "nixscore", ignore=ignore
    )
    shutil.copytree(
        REPO / "scripts" / "nixbus", dst / "scripts" / "nixbus", ignore=ignore
    )
    return dst


def _run(home: Path):
    """Run the SHIPPED gate against `home`."""
    return gate.run(Mode.VERIFY, Context(nix_home=home, mode=Mode.VERIFY))


def _break(home: Path, old: str, new: str) -> None:
    """One textual edit to the copied store, asserted to have landed."""
    target = home / STORE_MODULE
    text = target.read_text(encoding="utf-8")
    assert old in text, f"plant anchor {old!r} is not in the copied store"
    broken = text.replace(old, new, 1)
    assert broken != text, "the plant changed nothing"
    target.write_text(broken, encoding="utf-8")


# ---------------------------------------------------------------------------
# The unbroken half — asserted first, so every plant below is a PAIR
# ---------------------------------------------------------------------------


def test_the_gate_PASSES_the_store_as_shipped(home: Path) -> None:
    result = _run(home)
    assert result.status is Status.PASS, result.detail
    evidence = result.evidence or ""
    assert "SURVIVED" in evidence
    assert "EXACTLY" in evidence
    assert "ARCHIVED != ABSENT" in evidence
    assert "RESTORED" in evidence
    assert "ATOMIC" in evidence
    assert "NON-VACUITY" in evidence


# ---------------------------------------------------------------------------
# PLANT 1 — a store keyed to the PROCESS instead of to the pair (§6.6:430)
# ---------------------------------------------------------------------------


def test_the_gate_REDDENS_when_the_store_is_keyed_to_the_process(home: Path) -> None:
    # The counterfeit §6.6 exists to rule out: a store whose file name carries
    # the pid round-trips perfectly inside one process and loses everything at
    # the process boundary. Only a real death can see it.
    _break(
        home,
        "        self.path = Path(path)",
        "        self.path = Path(f'{path}.{os.getpid()}')",
    )
    result = _run(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.status
    assert "did NOT persist across process death" in result.detail
    assert "ScoreStore._commit" in result.site


# ---------------------------------------------------------------------------
# PLANT 2 — an archive that takes the NEIGHBOURS too (§6.6:431 "exactly")
# ---------------------------------------------------------------------------


def test_the_gate_REDDENS_when_archival_removes_more_than_that_strategy(
    home: Path,
) -> None:
    # `staying` is every pair NOT belonging to the quarantined strategy.
    # Emptying it is wholesale truncation — invisible to any single-strategy
    # fixture, which is why the gate seeds three strategies over two symbols.
    _break(
        home,
        "        staying = {k: v for k, v in self._live.items() if k[0] != strategy_id}",
        "        staying = {}",
    )
    result = _run(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.status
    assert "did not remove EXACTLY that strategy's rows" in result.detail
    assert "archive_strategy" in result.site


# ---------------------------------------------------------------------------
# PLANT 3 — archived becomes DESTROYED (§6.6:431 "archived, not destroyed")
# ---------------------------------------------------------------------------


def test_the_gate_REDDENS_when_archival_destroys_instead_of_archiving(
    home: Path,
) -> None:
    _break(home, "        merged.update(moving)", "        merged.update({})")
    result = _run(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.status
    assert "archived, not destroyed" in result.detail
    assert "prose" in result.detail
    assert "ScoreStore.presence" in result.site


# ---------------------------------------------------------------------------
# PLANT 4 — restore returns rows that are not the rows archived (§12.11:779)
# ---------------------------------------------------------------------------


def test_the_gate_REDDENS_when_restore_does_not_rehydrate_the_same_values(
    home: Path,
) -> None:
    _break(
        home,
        "        live.update(archive.rows)",
        "        live.update({k: dataclasses.replace(v, realized_ema=0.0)"
        " for k, v in archive.rows.items()})",
    )
    result = _run(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.status
    assert "not a recomputation" in result.detail
    assert "restore_strategy" in result.site


# ---------------------------------------------------------------------------
# PLANT 5 — restoring a never-archived strategy goes SILENT
# ---------------------------------------------------------------------------


def test_the_gate_REDDENS_when_a_restore_of_an_unknown_strategy_is_silent(
    home: Path,
) -> None:
    _break(
        home,
        "                    f\"{_SITE}: '{operator}' asked to restore {strategy_id!r}, which \"",
        '                    "nothing to do "',
    )
    result = _run(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.status
    assert "does NOT name" in result.detail
    assert "silent no-op" in result.detail


# ---------------------------------------------------------------------------
# PLANT 6 — a NON-ATOMIC durable write, so a kill can tear the document
# ---------------------------------------------------------------------------


def test_the_gate_REDDENS_when_the_durable_write_is_not_atomic(home: Path) -> None:
    # The plant is the design this module exists to refuse: truncate the target
    # and write into it. A victim killed mid-write leaves a file that is neither
    # the old document nor the new one, and the next process cannot read it.
    _break(
        home,
        """        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.path)
        except OSError:""",
        """        try:
            os.close(fd)
            os.unlink(temp_name)
            with open(self.path, "wb") as handle:
                for _at in range(0, len(payload), 64):
                    handle.write(payload[_at:_at + 64])
                    handle.flush()
                    time.sleep(0.002)
        except OSError:""",
    )
    result = _run(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.status
    assert "left a store the next process could not read" in result.detail
    assert (
        "half-archived" in result.detail or "whole previous document" in result.detail
    )
    assert "ScoreStore._commit" in result.site


# ---------------------------------------------------------------------------
# The gate must not PASS when it cannot see its subject at all (§17)
# ---------------------------------------------------------------------------


def test_the_gate_CANNOT_MEASURE_when_the_store_is_absent(home: Path) -> None:
    (home / STORE_MODULE).unlink()
    result = _run(home)
    assert result.status is Status.CANNOT_MEASURE
    assert "store.py" in result.detail


# ---------------------------------------------------------------------------
# The non-vacuity guard is itself asserted — a fixture that cannot make
# "exactly" a real claim must BLOCK the verdict rather than green it
# ---------------------------------------------------------------------------


def test_a_single_strategy_fixture_is_refused_as_vacuous() -> None:
    single = {("alpha", "ES"): (1.0, 1), ("alpha", "NQ"): (2.0, 1)}
    why = gate._shape_defect(single)  # pylint: disable=protected-access
    assert "not entangled enough" in why
    assert "1 strategies" in why or "2 strategies" in why


def test_the_shipped_fixture_shape_is_accepted() -> None:
    entangled = {
        ("alpha", "ES"): (1.0, 1),
        ("alpha", "NQ"): (2.0, 1),
        ("beta", "ES"): (3.0, 1),
        ("gamma", "NQ"): (4.0, 1),
    }
    assert gate._shape_defect(entangled) == ""  # pylint: disable=protected-access
