"""ARC 031 / Stage 2 — the can-fail suite for `checks/check_allocator_pathway.py`.

Non-vacuity first (the real tree passes), then one plant per arm into a COPY
under `tmp_path`, each of which must FAIL and NAME its site, then the plant
removed and the same tree green.

**No plant touches a production artifact** (doctrine C.8). The `home` fixture
copies the whole `nixalloc` package plus the frozen Limiter seam and the risk
spec, so a plant edits the copy and the SHIPPED gate's own bytes are driven
against it. The real tree is only ever READ.

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

import check_allocator_pathway as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)

COPIED = (
    "scripts/nixalloc/__init__.py",
    "scripts/nixalloc/seam.py",
    "scripts/nixalloc/caps.py",
    "scripts/nixalloc/contention.py",
    "scripts/nixalloc/mirror.py",
    "scripts/nixalloc/sizing.py",
    "scripts/nixalloc/wiring.py",
    "scripts/nixrisk/__init__.py",
    "scripts/nixrisk/seam.py",
    "scripts/nixrisk/picture.py",
    "docs/nics_risk_subsystem_spec_v1.3.md",
)

WIRING = "scripts/nixalloc/wiring.py"
SIZING = "scripts/nixalloc/sizing.py"


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """A throwaway tree carrying COPIES of the whole composed pathway."""
    for rel in COPIED:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / rel, target)
    return tmp_path


def _run(nix_home: Path):
    return gate.run(Mode.VERIFY, Context(nix_home=nix_home, mode=Mode.VERIFY))


def _plant(home: Path, rel: str, old: str, new: str) -> None:
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


def test_the_REAL_tree_and_the_COPY_both_pass(home: Path) -> None:
    """A gate that cannot pass on a clean pathway measures nothing on a dirty one."""
    live = _run(REPO)
    assert live.status is Status.PASS, live.detail
    assert "5 arms" in (live.evidence or ""), live.evidence
    assert "NOT proven here" in (live.evidence or ""), (
        "the evidence must state its own ceiling, or a green reads as coverage "
        "of the wire and of the Limiter's Phase B"
    )
    copied = _run(home)
    assert copied.status is Status.PASS, copied.detail


def test_a_MISSING_pathway_is_cannot_measure_never_a_PASS(tmp_path: Path) -> None:
    """§17: a property proven while its subject is unavailable is not proven."""
    result = _run(tmp_path)
    assert result.status is Status.CANNOT_MEASURE, result
    assert "never a PASS" in (result.detail or ""), result.detail


def test_the_gate_reads_the_tree_it_was_GIVEN_not_the_live_repo(home: Path) -> None:
    """D3.124's class: `_preamble` appends the REAL scripts/ to sys.path forever.

    Proven by planting into the COPY only. If the gate resolved `nixalloc.*` by
    name it would load the pristine live package and report PASS.
    """
    _plant(
        home,
        WIRING,
        "        return self.proposal.reaches_broker",
        "        return True",
    )
    result = _run(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, (
        "the gate passed on a sabotaged COPY — it is reading the live tree, "
        f"not the tree it was given: {result.detail}"
    )


# --------------------------------------------------------------------------
# ONE PLANT PER ARM
# --------------------------------------------------------------------------


def test_ARM1_a_pathway_that_SIZES_a_dead_signal_reddens(home: Path) -> None:
    """§16 U1: never size a dead signal."""
    _plant(
        home,
        SIZING,
        "        drop = self._fast_drop(strategy_id, symbol)\n"
        "        if drop is not None:\n"
        "            return drop\n",
        "        drop = self._fast_drop(strategy_id, symbol)\n"
        "        if drop is not None and False:\n"
        "            return drop\n",
    )
    result = _run(home)
    _red(result, site_contains="[dead]", why_contains="a dead signal was not dropped")


def test_ARM1_a_pathway_that_cannot_tell_STALE_from_DEAD_reddens(home: Path) -> None:
    """§0i / §12.7 — and the plant is chosen for what it PROVES.

    Sabotaging `MirrorSnapshot.sizeable` alone changes nothing, which is real
    defence in depth rather than a gap: `sizing.propose` checks
    `not snapshot.sizeable OR snapshot.picture is None`, so a stale mirror
    with no picture is still refused. MEASURED before this plant was written.

    The plant that does bite is the one that collapses the refusal's IDENTITY:
    a stale mirror reported as `NOT_TRADABLE` is indistinguishable from a dead
    signal, and §12.7's whole hazard is that a mirror which never heard from
    the publisher looks exactly like a quiet, healthy feed.
    """
    _plant(
        home,
        SIZING,
        "                ProposalOutcome.STALE_MIRROR,",
        "                ProposalOutcome.NOT_TRADABLE,",
    )
    result = _run(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    assert "stale:" in (result.site or ""), result.site
    assert "rather than refused" in (result.detail or ""), result.detail
    assert "collapsed into" in (result.detail or ""), (
        "the distinctness arm must ALSO fire — that is the property that makes "
        f"the stale class visible at all: {result.detail}"
    )


def test_ARM1_a_pathway_that_MANUFACTURES_a_size_on_a_zero_stop_reddens(
    home: Path,
) -> None:
    """§7:483 — the Limiter denies; the Allocator does not invent a size."""
    _plant(
        home,
        SIZING,
        "        if stop_ticks <= 0:",
        "        if stop_ticks < 0:",
    )
    result = _run(home)
    _red(
        result,
        site_contains="[zero-stop]",
        why_contains="must not manufacture a size",
    )


def test_ARM2_a_cap_measured_against_MAX_instead_of_SUM_reddens(home: Path) -> None:
    """Sub-agent C's own §0a finding, re-driven through the composed adapter."""
    _plant(
        home,
        "scripts/nixalloc/caps.py",
        "        total += dollar_risk(exposure, config)",
        "        total = max(total, dollar_risk(exposure, config))",
    )
    result = _run(home)
    _red(
        result,
        site_contains="[summation]",
        why_contains="the adapter is not summing the bucket",
    )


def test_ARM2_a_case_that_no_longer_DISCRIMINATES_is_itself_a_finding(
    home: Path,
) -> None:
    """§7.12/3 — a discriminating case that quietly stops discriminating.

    Planted by making both held positions price identically, at which point
    sum and max agree and ARM 2's comparison could never fail. The arm must
    report that rather than reporting a pass.
    """
    _plant(
        home,
        "scripts/nixalloc/caps.py",
        "def dollar_risk(exposure: Exposure, config: CapConfig) -> float:",
        "def dollar_risk(exposure: Exposure, config: CapConfig) -> float:\n"
        "    if True:\n"
        "        return 0.0",
    )
    result = _run(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    assert "[summation]" in (result.site or ""), result.site
    assert "no longer DISCRIMINATES" in (result.detail or ""), result.detail


def test_ARM3_an_unpriced_position_valued_at_ZERO_reddens(home: Path) -> None:
    """D3.136: the false green in the ADMITTING direction.

    ARC 032 re-anchored this plant. The defect planted is IDENTICAL — a row
    with no usable stop distance dropped from the report instead of counted as
    unpriced — but it is now planted against the published `stop_distance`
    rather than against a lookup in a side table that no longer exists.
    """
    _plant(
        home,
        WIRING,
        "            if stop <= 0:\n"
        "                unpriced.append(row.trade_id)\n"
        "                continue\n",
        "            if stop <= 0:\n                continue\n",
    )
    result = _run(home)
    _red(
        result,
        site_contains="D3.136",
        why_contains="reported a CLEAN cap",
    )


def test_ARM3_an_UNBUCKETED_row_dropped_SILENTLY_reddens(home: Path) -> None:
    """THE SECOND DOOR (ARC 032), and the plant is the pre-ARC-032 code itself.

    Replacing the three-way classification with the one comprehension this
    module shipped before ARC 032 — `BUCKET_OF.get(row.symbol) is bucket`, no
    third class, no counter — is exactly how a contract-spelled row left the
    bucket with nothing said. If ARM 3 (C) stays green on it, the report is
    decoration.
    """
    _plant(
        home,
        WIRING,
        "            if row_bucket is None:\n"
        '                unbucketed.append(f"{row.trade_id}:{row.symbol}")\n'
        "                continue\n",
        "            if row_bucket is None:\n                continue\n",
    )
    result = _run(home)
    _red(
        result,
        site_contains="D3.136",
        why_contains="was dropped from every bucket",
    )


def test_ARM3_a_cap_complete_that_IGNORES_the_unbucketed_class_reddens(
    home: Path,
) -> None:
    """`cap_complete` must fold BOTH classes, or it reports a lie by omission.

    A caller asking "did the cap see the whole bucket?" gets one boolean. If
    that boolean only knows about unpriced rows, an unbucketed table reads as a
    complete one — which is the D3.136 report shape reproduced one level up,
    inside the very predicate that exists to prevent it.
    """
    _plant(
        home,
        WIRING,
        "        return not self.cap_incomplete and not self.cap_unbucketed",
        "        return not self.cap_incomplete",
    )
    result = _run(home)
    _red(
        result,
        site_contains="D3.136",
        why_contains="reported a COMPLETE cap",
    )


def test_ARM3_a_rationale_that_HIDES_the_blindness_reddens(home: Path) -> None:
    """§16 U5: the Limiter's event log must be able to audit the blindness."""
    _plant(
        home,
        WIRING,
        '            f"; {len(unpriced)} held position(s) in {query.bucket.value} could "\n'
        '            "NOT be priced (published stop_distance absent or non-positive), "\n'
        '            "so this ceiling is measured over an INCOMPLETE bucket"\n',
        '            ""\n',
    )
    result = _run(home)
    _red(
        result,
        site_contains="D3.136",
        why_contains="does not carry the blindness",
    )


def test_ARM4_a_headroom_RECOMPUTED_from_the_rows_reddens(home: Path) -> None:
    """§16 U2: one source of truth. The published `committed` is the figure."""
    _plant(
        home,
        SIZING,
        "    return deployable_pct * picture.balance - picture.committed",
        "    return deployable_pct * picture.balance - sum(\n"
        "        row.margin for row in picture.positions\n"
        "    )",
    )
    result = _run(home)
    _red(
        result,
        site_contains="[partial-fill]",
        why_contains="followed the position rows instead of the published",
    )


def test_ARM5_an_emitted_object_that_REACHES_A_BROKER_reddens(home: Path) -> None:
    """§2: the authority invariant at the seam."""
    _plant(
        home,
        WIRING,
        "    @property\n"
        "    def reaches_broker(self) -> bool:\n"
        '        """Always False — §2. The pathway emits proposals, never orders."""\n'
        "        return self.proposal.reaches_broker",
        "    @property\n"
        "    def reaches_broker(self) -> bool:\n"
        '        """Planted."""\n'
        "        return True",
    )
    result = _run(home)
    _red(
        result,
        site_contains="AllocatorPathway",
        why_contains="claims it reaches a broker",
    )


def test_ARM5_a_pathway_that_grows_a_PLACE_verb_reddens(home: Path) -> None:
    """Proven by ATTEMPT — `getattr`, not a source scan."""
    _plant(
        home,
        WIRING,
        "    def propose(\n        self,\n        strategy_id: str,",
        "    def place(self, order: object) -> None:\n"
        '        """Planted authority."""\n\n'
        "    def propose(\n        self,\n        strategy_id: str,",
    )
    result = _run(home)
    _red(
        result,
        site_contains="AllocatorPathway.place",
        why_contains="a verb it exposes is authority it has",
    )


def test_a_cap_that_RAISES_into_the_pass_reddens(home: Path) -> None:
    """§6.6's rule generalised: a component outage must never halt order flow.

    The adapter converts every refusal into an admitted-zero verdict. Remove
    that and `caps.admit`'s fail-closed guard kills the pass instead — which
    the gate sees as a CANNOT_MEASURE (the pathway raised), never a pass.
    """
    _plant(
        home,
        WIRING,
        "        except caps.BucketCapError as exc:\n"
        "            return BucketVerdict(\n"
        "                contracts=0,\n"
        "                used=0.0,\n"
        "                ceiling=0.0,\n"
        '                note=f"§7 cap REFUSED and the pass denies rather than dies: {exc}",\n'
        "            )\n",
        "        except caps.BucketCapError:\n            raise\n",
    )
    _plant(
        home,
        "scripts/nixalloc/caps.py",
        "    if contracts <= 0:",
        "    if contracts >= 0:",
    )
    result = _run(home)
    assert result.status in (Status.FAIL_NEEDS_OPERATOR, Status.CANNOT_MEASURE), result
    assert "BucketCapError" in (result.detail or "") or "[bucket]" in (
        result.site or ""
    ), result


# --------------------------------------------------------------------------
# RESTORE
# --------------------------------------------------------------------------


def test_the_plant_REMOVED_returns_the_same_tree_to_green(home: Path) -> None:
    """A red that does not clear on repair is a broken gate, not a finding."""
    original = (home / WIRING).read_text(encoding="utf-8")
    _plant(
        home,
        WIRING,
        "        return self.proposal.reaches_broker",
        "        return True",
    )
    assert _run(home).status is Status.FAIL_NEEDS_OPERATOR
    (home / WIRING).write_text(original, encoding="utf-8")
    restored = _run(home)
    assert restored.status is Status.PASS, restored.detail
    assert (home / WIRING).read_bytes() == (REPO / WIRING).read_bytes(), (
        "the restored copy is not byte-identical to the shipped subject"
    )
