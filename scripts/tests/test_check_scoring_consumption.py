"""ARC 036 / sub-agent E — the can-fail suite for `check_scoring_consumption.py`.

Non-vacuity first (the real tree passes, and the COPY of it passes too), then
one plant per arm into a COPY under `tmp_path`, each of which must FAIL or
refuse and NAME its site and its reason, then the plant removed and the same
tree green again.

**No plant touches a production artifact** (doctrine C.8). The `home` fixture
copies the whole composed Allocator plus the frozen §6.6 scoring seam and the
state bus underneath it, so a plant edits the copy while the SHIPPED gate's own
bytes are driven against it. The real tree is only ever READ.

**Every plant is a defect in the SUBJECT, not in the gate's own arithmetic.**
Each one is a plausible edit somebody could make to `scripts/nixalloc/wiring.py`
and each leaves a different arm as the only one that notices:

| plant | what it breaks | arm that must catch it |
|---|---|---|
| rank against `None` | the ranking is read and thrown away | flip |
| deny when the table is down | §6.6:467-468, backwards | outage |
| never withhold in-race capital | the race stops contending | non-vacuity |
| recompute the EMA in `row` | §6.6:461-463 / §11:595 | read-path |
| read the table in `__init__` | §16's per-GO-only work | cost |

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

import check_scoring_consumption as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)

#: HAND-MAINTAINED, and the maintenance is the point: one new first-party import
#: inside a subject silences this whole suite with "cannot import the Allocator
#: out of /tmp/...: ModuleNotFoundError" while the gate stays green on the real
#: tree. `test_00` exists to make that failure loud instead of silent.
COPIED = (
    "scripts/nixalloc/__init__.py",
    "scripts/nixalloc/seam.py",
    "scripts/nixalloc/caps.py",
    "scripts/nixalloc/contention.py",
    "scripts/nixalloc/lifecycle.py",
    "scripts/nixalloc/mirror.py",
    "scripts/nixalloc/sizing.py",
    "scripts/nixalloc/wiring.py",
    "scripts/nixrisk/__init__.py",
    "scripts/nixrisk/seam.py",
    "scripts/nixrisk/picture.py",
    "scripts/nixscore/__init__.py",
    "scripts/nixscore/seam.py",
    "scripts/nixbus/__init__.py",
    "scripts/nixbus/statebus.py",
)

WIRING = "scripts/nixalloc/wiring.py"


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """A throwaway tree carrying COPIES of the whole consumption path."""
    for rel in COPIED:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / rel, target)
    return tmp_path


def _run(nix_home: Path):
    return gate.run(Mode.VERIFY, Context(nix_home=nix_home, mode=Mode.VERIFY))


def _plant(where: Path, rel: str, old: str, new: str) -> None:
    """Rewrite a COPIED file. Fails loudly if the anchor moved or is ambiguous."""
    path = where / rel
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, (
        f"{rel}: anchor appears {text.count(old)} times, not once — the plant "
        "would measure something other than what it names"
    )
    path.write_text(text.replace(old, new), encoding="utf-8")


def _unplant(where: Path, rel: str) -> None:
    """Restore one copied file from the real tree, so green-after is honest."""
    shutil.copy(REPO / rel, where / rel)


# ==========================================================================
# 0 — NON-VACUITY. The real tree and the untouched copy both pass.
# ==========================================================================


def test_00_the_REAL_TREE_passes_and_the_evidence_names_the_FLIP() -> None:
    """A gate that cannot pass on a correct tree measures nothing usable."""
    result = _run(REPO)
    assert result.status is Status.PASS, result.detail
    assert "FLIPPED" in result.evidence, result.evidence
    assert "outage route(s)" in result.evidence, result.evidence


def test_02_the_untouched_COPY_UNDER_TMP_passes(home: Path) -> None:
    """The same, driven out of `tmp_path` — the tree every plant starts from."""
    result = _run(home)
    assert result.status is Status.PASS, result.detail


def test_03_every_ARM_proves_it_can_FAIL_on_a_planted_answer() -> None:
    """The gate's own controls, asserted directly rather than trusted."""
    blind, why = gate.arms_can_fail()
    assert blind == "", f"{blind} arm cannot fail: {why}"


# ==========================================================================
# 1 — THE FLIP. A ranking that is read and thrown away.
# ==========================================================================


def test_10_a_RANKING_READ_AND_DISCARDED_is_a_FAIL_naming_the_flip(
    home: Path,
) -> None:
    """The defect this whole gate exists for: the table changes nothing.

    `contention.rank(contenders, None)` still consults §6.6's fallback, still
    produces an ordering, and still leaves every un-flipped assertion true —
    the head of the race is the earlier arrival, which is ALSO the higher-ranked
    pair in the un-flipped direction. Only reversing the pair-rows separates
    them.
    """
    _plant(
        home,
        WIRING,
        "ranking = contention.rank(contenders, self._ranking)",
        "ranking = contention.rank(contenders, None)",
    )
    result = _run(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    assert "propose_contended" in result.site, result.site
    assert "REVERSING" in result.detail, result.detail
    assert "not a function of the ranking table" in result.detail, result.detail
    _unplant(home, WIRING)
    assert _run(home).status is Status.PASS


# ==========================================================================
# 2 — THE OUTAGE. §6.6:467-468 stated backwards.
# ==========================================================================


def test_20_a_DENY_WHEN_SCORING_IS_DOWN_is_a_FAIL_naming_the_halt(
    home: Path,
) -> None:
    """The hazard, planted: an unusable table becomes a refusal.

    This is the one that would look most like caution in review — "if we cannot
    rank them, do not size either" — and §6.6:467-468 forbids exactly it.
    """
    _plant(
        home,
        WIRING,
        "        by_pair = {(go.strategy_id, go.symbol): go for go in gos}",
        "        if ranking.is_fallback:\n"
        "            return ContentionOutcome(\n"
        "                ranking=ranking, reports=(), order=(), pairwise=None,\n"
        "                span_days=None, table_fresh=False, reason='scoring down',\n"
        "            )\n"
        "        by_pair = {(go.strategy_id, go.symbol): go for go in gos}",
    )
    result = _run(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    assert "outage" in result.site, result.site
    assert "must NEVER halt order flow" in result.detail, result.detail
    assert "no mirror injected at all" in result.detail, result.detail
    _unplant(home, WIRING)
    assert _run(home).status is Status.PASS


def test_21_a_MIRROR_THAT_RAISES_is_driven_and_must_NOT_reach_the_caller() -> None:
    """§6.6:467-468 against a publisher that just died, on the REAL tree.

    Driven rather than asserted about: the gate's own outage set includes a
    mirror whose every verb throws, and a wiring that let the exception out
    would make this gate CANNOT_MEASURE with `gate raised RuntimeError`.
    """
    result = _run(REPO)
    assert result.status is Status.PASS, result.detail
    assert "7 outage route(s)" in result.evidence, result.evidence


# ==========================================================================
# 3 — NON-VACUITY. A race that stopped contending.
# ==========================================================================


def test_30_a_RACE_THAT_WITHHOLDS_NOTHING_is_CANNOT_MEASURE_not_a_pass(
    home: Path,
) -> None:
    """Both contenders fit, so any ordering is correct and nothing was measured.

    CANNOT_MEASURE and not FAIL, deliberately: the subject is not wrong about
    who wins, the instrument has stopped being able to tell.
    """
    _plant(
        home,
        WIRING,
        "        self._race.spent = withheld + self._committed_by(report, go.symbol)",
        "        self._race.spent = withheld",
    )
    result = _run(home)
    assert result.status is Status.CANNOT_MEASURE, result.detail
    assert "non-vacuity" in result.site, result.site
    assert "cannot satisfy them all" in result.detail, result.detail
    _unplant(home, WIRING)
    assert _run(home).status is Status.PASS


# ==========================================================================
# 4 — THE READ PATH. A consumer that computes.
# ==========================================================================


def test_40_a_CONSUMER_THAT_RECOMPUTES_THE_EMA_is_a_FAIL_naming_the_site(
    home: Path,
) -> None:
    """§6.6:461-463 / §11:595. The output is right; the shape is the defect."""
    _plant(
        home,
        WIRING,
        "            score=hit.realized_ema,",
        "            score=hit.realized_ema * (self.now or 1.0),",
    )
    result = _run(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    assert f"{WIRING}:row" in result.site, result.site
    assert "never math" not in result.detail or "Mult" in result.detail, result.detail
    assert "hot-path violation" in result.detail, result.detail
    _unplant(home, WIRING)
    assert _run(home).status is Status.PASS


def test_41_a_RENAMED_READ_PATH_is_a_NON_VACUITY_fail_not_a_silent_pass(
    home: Path,
) -> None:
    """A scan that finds none of the functions it judges reports nothing.

    §7.12/2: an empty expected set agrees silently with an empty measured one.
    Renaming `_pairwise` leaves the module importable and every behavioural arm
    green — only the read-path scan's own floor notices that it is now judging
    two functions where it names three.
    """
    _plant(home, WIRING, "def _pairwise(\n", "def _pairwise_read(\n")
    _plant(home, WIRING, "self._pairwise(contenders", "self._pairwise_read(contenders")
    result = _run(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    assert "non-vacuity" in result.site, result.site
    assert "scan over nothing" in result.detail, result.detail
    _unplant(home, WIRING)
    assert _run(home).status is Status.PASS


# ==========================================================================
# 5 — THE COST. §16's per-GO-only work.
# ==========================================================================


def test_50_a_TABLE_READ_AT_CONSTRUCTION_is_a_FAIL_naming_the_per_GO_rule(
    home: Path,
) -> None:
    """A read that happens without a GO is a cost on whatever constructs it."""
    _plant(
        home,
        WIRING,
        "        self._ranking = None if ranking is None else _MirrorRankingTable(ranking)",
        "        self._ranking = None if ranking is None else _MirrorRankingTable(ranking)\n"
        "        if ranking is not None:\n"
        "            try:\n"
        "                ranking.fresh()\n"
        "            except Exception:  # noqa: BLE001\n"
        "                pass",
    )
    result = _run(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    assert "AllocatorPathway" in result.site, result.site
    assert "NO GO proposed" in result.detail, result.detail
    assert "per-GO-only work" in result.detail, result.detail
    _unplant(home, WIRING)
    assert _run(home).status is Status.PASS


# ==========================================================================
# 6 — §17. An unavailable subject is never a PASS.
# ==========================================================================


def test_60_a_MISSING_SUBJECT_is_CANNOT_MEASURE_never_a_PASS(tmp_path: Path) -> None:
    """Rule 10 / §17: a property proven while its subject is absent is not proven.

    MEASURED, and it is the interesting half: an EMPTY tree does not produce an
    `ImportError`. `_preamble` has already seeded `sys.path` with the REAL
    repository, so `import nixalloc.wiring` succeeds and resolves to the live
    tree — and every arm would then report on the live tree while the verdict
    claimed to be about `tmp_path`. The `__file__` comparison in `load` is what
    catches it, which is exactly the defect that comparison was written for.
    """
    result = _run(tmp_path)
    assert result.status is Status.CANNOT_MEASURE, result.detail
    assert "is not the tree that was named" in result.detail, result.detail
    assert str(tmp_path) in result.detail, result.detail


def test_61_a_SUBJECT_RESOLVED_OUTSIDE_HOME_is_refused(home: Path) -> None:
    """The gate must measure the tree it was HANDED, not the one on `sys.path`.

    Driven by deleting the copy's `wiring.py` while leaving the rest: the import
    would otherwise fall through to the real repository that the check preamble
    already seeded onto `sys.path`, and every arm would then report on the live
    tree while the verdict claimed to be about `home`.
    """
    (home / WIRING).unlink()
    result = _run(home)
    assert result.status is Status.CANNOT_MEASURE, result.detail
    assert "nixalloc.wiring" in result.detail, result.detail


# ==========================================================================
# 7 — The declaration preamble the runner reads statically (§4.4).
# ==========================================================================


def test_70_the_DECLARATIONS_are_present_and_name_the_subject() -> None:
    """`SUBJECTS`, `RESOURCES` and `ON_FAIL` are read by AST, never by import."""
    assert WIRING in gate.SUBJECTS, gate.SUBJECTS
    assert gate.ON_FAIL == "continue"
    assert gate.RESOURCES == ("interpreter:sys.modules", "interpreter:sys.path")
    assert gate.CORRECTABLE is False
    assert gate.NON_CORRECTABLE_REASON.strip()
