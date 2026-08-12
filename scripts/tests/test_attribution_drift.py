"""Tests for `scripts/tests/attribution_drift.py` (ARC 027 / D1).

**The load-bearing test in this file is `test_the_detector_fires_on_a_planted_
order_dependent_claim`.** Everything else guards a way the instrument could go
quiet; that one is the §0e artifact — a committed, runnable control that plants
a genuinely order-dependent claim and requires the detector to report it. A
drift detector that has never been seen to fire is a green light.

Two controls are exercised, not one:

* `CONTROL_SHARED_CACHE` — the mechanism, with the interpreter removed: one
  on-disk cache, first runner pays.
* `CONTROL_LAZY_IMPORT` — ARC 026's shape verbatim: a lazy import inside `run()`
  writing a bytecode cache inside the armed observation window. It also carries
  the negative measurement for normalisation rule 1 (see
  `test_without_the_pyc_rule_arc026s_own_defect_demotes_to_unstable`), which is
  the only evidence that the rule is doing work rather than decorating.

Every assertion here keys on the REASON — the claim, the owning checks, the
refusal text — never on a bare exit code or a bare truthiness.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

sys.path.insert(0, str(Path(__file__).resolve().parent))

# pylint: disable=wrong-import-position
# The `sys.path` bootstrap above must run BEFORE this import.
import attribution_drift as ad  # pylint: disable=import-error

# pylint: enable=wrong-import-position

# ---------------------------------------------------------------------------
# THE CONTROL — the detector must be seen to fire.
# ---------------------------------------------------------------------------


def test_the_detector_fires_on_a_planted_order_dependent_claim(tmp_path: Path) -> None:
    """A shared on-disk cache, first runner pays: the detector must name it."""
    report = ad.self_test(tmp_path, ad.CONTROL_SHARED_CACHE)

    assert not report.clean, "the planted claim was not reported"
    entries = [d for d in report.order_dependent if d.claim.endswith("/shared/entry")]
    assert entries, (
        "the shared cache file itself was not among the findings: "
        f"{[d.claim for d in report.order_dependent]}"
    )
    owners = entries[0].per_order
    assert set(owners) == {"plan-order", "reversed-within-block"}, owners
    # The FINDING is that the two orders disagree about who owns the claim, and
    # the report must say so by naming both checks — not merely by disagreeing.
    assert owners["plan-order"] != owners["reversed-within-block"], owners
    assert owners["plan-order"] == ["check_ctl_drift_0"], owners
    assert owners["reversed-within-block"] == ["check_ctl_drift_5"], owners
    # Volatility is not what fired: the planted path is deterministic.
    assert not report.unstable, [d.render() for d in report.unstable]


def test_the_detector_fires_on_arc026s_own_pyc_shape(tmp_path: Path) -> None:
    """The historical defect, reproduced: a lazy import inside the armed window."""
    report = ad.self_test(tmp_path, ad.CONTROL_LAZY_IMPORT)

    pyc = [d for d in report.order_dependent if ".pyc." in d.claim]
    assert pyc, (
        "the bytecode-cache write was not reported as order-dependent; found "
        f"{[d.claim for d in report.order_dependent]}"
    )
    assert pyc[0].claim.endswith(".pyc.<NONCE>"), pyc[0].claim
    assert pyc[0].per_order["plan-order"] == ["check_ctl_drift_0"], pyc[0].per_order
    assert pyc[0].per_order["reversed-within-block"] == ["check_ctl_drift_5"], pyc[
        0
    ].per_order


def test_without_the_pyc_rule_arc026s_own_defect_demotes_to_unstable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The negative measurement that justifies normalisation rule 1.

    `importlib` writes bytecode as `<name>.pyc.<id(path)>`, and the integer is
    per-process. So ARC 026's own claim is volatile-named AND order-dependent:
    with rule 1 removed, the A/A' baseline classifies it UNSTABLE and **the
    bytecode-cache finding is LOST**. This is the evidence that the rule earns
    its place; without this test the table is prose.

    Note what does NOT happen: the run is not clean. The `__pycache__` DIRECTORY
    is created at a deterministic path, so a sibling claim still fires and the
    detector still refuses. That is precisely why this test asserts on the
    CLAIM and not on the verdict — a verdict-level assertion here would have
    passed while the finding it names had gone missing.
    """
    with_rule = ad.self_test(tmp_path / "with", ad.CONTROL_LAZY_IMPORT)
    assert any(".pyc." in d.claim for d in with_rule.order_dependent)

    stripped = tuple(r for r in ad.NORMALISERS if r[0] != ad.PYC_RULE)
    assert len(stripped) == len(ad.NORMALISERS) - 1, (
        "the rule under test was not removed — a negative control that removes "
        "nothing measures nothing"
    )
    monkeypatch.setattr(ad, "NORMALISERS", stripped)
    without = ad.self_test(tmp_path / "without", ad.CONTROL_LAZY_IMPORT)

    assert not any(".pyc." in d.claim for d in without.order_dependent), (
        "rule 1 removed and the bytecode claim STILL classified as drift — the "
        "rule would then be doing no work"
    )
    assert any(".pyc." in d.claim for d in without.unstable), (
        "the bytecode claim vanished entirely instead of demoting to UNSTABLE: "
        f"{[d.claim for d in without.unstable]}"
    )


# ---------------------------------------------------------------------------
# THE REFUSALS — every way this could report clean while measuring nothing.
# ---------------------------------------------------------------------------


def test_two_identical_orders_are_a_refusal_not_a_clean_sheet() -> None:
    """§7.12 #1. A reordering detector that does not reorder must refuse."""
    with pytest.raises(ad.RefusedError) as excinfo:
        ad.detect(
            checks_dir=ad.REPO / "checks",
            home=ad.REPO,
            plan=[["check_python_runtime"]],  # one member: every order is equal
            cold=lambda: 0,
            order_count=2,
            exclude=(),
        )
    assert "THE SAME ORDER" in str(excinfo.value), excinfo.value


def test_a_tiny_population_is_a_refusal() -> None:
    """§7.12 #4. Two checks cannot be reordered informatively.

    Two checks with NO declared relation to each other, so the refusal under
    test is the population floor and not the permutability assertion — which is
    what this test caught on its first run.
    """
    with pytest.raises(ad.RefusedError) as excinfo:
        ad.detect(
            checks_dir=ad.REPO / "checks",
            home=ad.REPO,
            plan=[["check_python_runtime", "check_price_ring"]],
            cold=lambda: 0,
            order_count=2,
            exclude=(),
        )
    message = str(excinfo.value)
    assert "credibility floor" in message and str(ad.MIN_CREDIBLE_CHECKS) in message


def test_a_silent_observer_is_a_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§7.12 #3. Zero claims reads identically to a population touching nothing."""
    names = [f"check_ctl_quiet_{i}" for i in range(ad.MIN_CREDIBLE_CHECKS + 1)]
    cold = ad.plant_control(
        tmp_path / "checks", tmp_path, ad.CONTROL_SHARED_CACHE, names
    )
    monkeypatch.setattr(ad, "observe_check", _empty)
    with pytest.raises(ad.RefusedError) as excinfo:
        ad.detect(
            tmp_path / "checks", tmp_path, [names], cold, order_count=2, exclude=()
        )
    assert "disarmed observer" in str(excinfo.value), excinfo.value


def _empty(_checks_dir, name, _home, **_kwargs):
    """An observation that recorded nothing — the disarmed-observer signature."""
    from nixverify.observe import ObservedRun  # pylint: disable=C0415

    return ObservedRun(check=name)


def test_an_intra_block_dependency_refuses_the_shuffle(tmp_path: Path) -> None:
    """Reordering is only legal because block members do not constrain each other.

    `optimize._levels` guarantees that by construction. It is asserted rather
    than trusted, because a hand-edited registry would take it away silently and
    the detector would then be measuring a plan the system would never run.
    """
    checks = tmp_path / "checks"
    ad.plant_control(checks, tmp_path, ad.CONTROL_SHARED_CACHE, ["check_ctl_a"])
    body = (checks / "check_ctl_a.py").read_text(encoding="utf-8")
    (checks / "check_ctl_b.py").write_text(
        body.replace("DEPENDS_ON = ()", 'DEPENDS_ON = ("check_ctl_a",)'),
        encoding="utf-8",
    )
    with pytest.raises(ad.RefusedError) as excinfo:
        ad.assert_permutable([["check_ctl_a", "check_ctl_b"]], checks)
    message = str(excinfo.value)
    assert "check_ctl_b" in message and "check_ctl_a" in message
    assert "may not" in message and "permuted" in message


# ---------------------------------------------------------------------------
# THE NORMALISATION TABLE — unit-tested directly, like `observe.covers()`.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # rule 1 — importlib._write_atomic's '{}.{}'.format(path, id(path))
        (
            "file-write:/x/__pycache__/m.cpython-314.pyc.124164211425776",
            "file-write:/x/__pycache__/m.cpython-314.pyc.<NONCE>",
        ),
        # rule 2 — tempfile's 8-char random name, FIRST segment under the root
        ("file-write:/tmp/j933mshi", "file-write:/tmp/<R8>"),
        ("file-write:/tmp/nixbus-gate-1q0j4sn3", "file-write:/tmp/nixbus-gate-<R8>"),
        (
            "file-write:/tmp/nixbus-gate-1q0j4sn3/ctl.ipc",
            "file-write:/tmp/nixbus-gate-<R8>/ctl.ipc",
        ),
        # rule 3 — secrets.token_hex(8)
        (
            "file-write:/home/x/checks/.plane2_control_ARC024CTL-af89922babc69678",
            "file-write:/home/x/checks/.plane2_control_ARC024CTL-<HEX>",
        ),
        # untouched: nothing in the table may generalise a path a check CHOSE
        ("subprocess:/usr/bin/git", "subprocess:/usr/bin/git"),
        ("socket:127.0.0.1:4002", "socket:127.0.0.1:4002"),
        ("unix-socket:/dev/log", "unix-socket:/dev/log"),
        ("file-write:/home/x/state/node_identity.json", None),
    ],
)
def test_normalise_abstracts_only_named_per_run_generators(
    raw: str, expected: str | None
) -> None:
    """Each rule abstracts exactly one named generator, and nothing else."""
    assert ad.normalise(raw) == (raw if expected is None else expected)


def test_the_two_prefixed_temp_roots_stay_distinct_claims() -> None:
    """Rule 2 is anchored so it cannot merge two different temp roots.

    `check_state_bus` claims BOTH `/tmp/<mkdtemp>` and `/tmp/nixbus-gate-<...>`
    in one run. A rule that collapsed the whole first segment would fuse them
    into one key and silently halve that check's claim set.
    """
    left = ad.normalise("file-write:/tmp/j933mshi")
    right = ad.normalise("file-write:/tmp/nixbus-gate-1q0j4sn3")
    assert left != right, (left, right)


# ---------------------------------------------------------------------------
# ORDER DERIVATION
# ---------------------------------------------------------------------------


def test_orders_permute_within_blocks_and_never_across_them() -> None:
    """A block boundary is a dependency level; nothing may cross it."""
    blocks = [["a"], ["b", "c", "d"], ["e"], ["f", "g"]]
    produced = ad.orders(blocks, exclude=(), count=4)
    labels = [label for label, _ in produced]
    assert labels == [
        "plan-order",
        "reversed-within-block",
        "shuffled-seed-0",
        "shuffled-seed-1",
    ]
    for _label, order in produced:
        assert order[0] == "a"
        assert set(order[1:4]) == {"b", "c", "d"}
        assert order[4] == "e"
        assert set(order[5:]) == {"f", "g"}


def test_the_excluded_self_executing_gate_is_not_swept() -> None:
    """`check_observed_resource_claims` re-executes the population; it is skipped."""
    blocks = ad.registry_blocks(ad.REPO / "checks" / "registry.json")
    _label, order = ad.orders(blocks, exclude=ad.SELF_EXECUTING, count=1)[0]
    assert "check_observed_resource_claims" not in order
    assert "check_python_runtime" in order


def test_the_shipped_registry_blocks_are_permutable() -> None:
    """The property the whole reordering rests on, asserted against what ships."""
    blocks = ad.registry_blocks(ad.REPO / "checks" / "registry.json")
    assert len(blocks) >= 2, blocks
    ad.assert_permutable(blocks, ad.REPO / "checks")


# ---------------------------------------------------------------------------
# COLD STATE
# ---------------------------------------------------------------------------


def test_clear_pycache_never_follows_or_deletes_a_symlinked_root(
    tmp_path: Path,
) -> None:
    """`.venv` and `state/` are symlinks back to the canonical tree in a worktree.

    An instrument that deleted through them would damage the thing it measures —
    and this project has already lost an arc to a sub-agent's git call reaching
    the canonical repository.
    """
    real = tmp_path / "real"
    (real / "__pycache__").mkdir(parents=True)
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)

    assert ad.clear_pycache([link]) == 0
    assert (real / "__pycache__").is_dir(), "deleted through a symlink"
    assert ad.clear_pycache([real]) == 1
    assert not (real / "__pycache__").exists()


def test_a_cold_reset_that_cleared_nothing_is_reported_not_hidden() -> None:
    """§7.12 #2. The class only exists on a cold cache; a warm run must say so."""
    empty = ad.Sweep("a", ("x",), {}, {}, {}, {}, cleared=0, elapsed_s=0.0)
    report = ad.compare([(empty, empty)])
    assert any("cleared NOTHING" in note for note in report.notes), report.notes


def test_lossy_normalisation_is_counted_and_reported() -> None:
    """Over-normalisation cannot create a cross-check finding, but it can mask one."""
    lossy = ad.Sweep(
        label="a",
        order=("check_x",),
        owners={"file-write:/tmp/<R8>": {"check_x"}},
        raw={"check_x": ("file-write:/tmp/aaaaaaaa", "file-write:/tmp/bbbbbbbb")},
        collapsed={"check_x": (2, 1)},
        errors={},
        cleared=1,
        elapsed_s=0.0,
    )
    report = ad.compare([(lossy, lossy)])
    assert report.clean
    assert any(
        "LOSSY" in note and "check_x (2 raw -> 1 keys)" in note for note in report.notes
    ), report.notes


def test_an_unobserved_check_is_reported_never_treated_as_clean() -> None:
    """A check that could not be observed is an unanswered question, not a pass."""
    broken = ad.Sweep(
        label="a",
        order=("check_x",),
        owners={},
        raw={"check_x": ()},
        collapsed={"check_x": (0, 0)},
        errors={"check_x": "observation timed out after 45.0s"},
        cleared=1,
        elapsed_s=0.0,
    )
    report = ad.compare([(broken, broken)])
    assert any("UNOBSERVED" in note and "timed out" in note for note in report.notes)


# ---------------------------------------------------------------------------
# CLASSIFICATION
# ---------------------------------------------------------------------------


def _sweep(label: str, owners: dict[str, set[str]]) -> ad.Sweep:
    """A Sweep carrying only an owners map — the input `compare` actually reads."""
    return ad.Sweep(label, ("x",), owners, {}, {}, {}, cleared=1, elapsed_s=0.0)


def test_a_claim_unstable_between_identical_orders_is_never_called_drift() -> None:
    """The A/A' baseline. 12 of this tree's 23 claims moved for this reason."""
    ref = _sweep("A", {"c": {"check_x"}})
    rep = _sweep("A", {"c": {"check_y"}})
    other = _sweep("B", {"c": {"check_z"}})
    report = ad.compare([(ref, rep), (other, other)])
    assert report.clean, [d.render() for d in report.order_dependent]
    assert [d.claim for d in report.unstable] == ["c"]
    # The reason must name the DISAGREEING pair, not merely the claim.
    assert report.unstable[0].per_order["A#1"] == ["check_x"]
    assert report.unstable[0].per_order["A#2"] == ["check_y"]


def test_a_claim_stable_in_one_order_and_moved_in_another_is_the_finding() -> None:
    """The whole rule, in one assertion."""
    ref = _sweep("A", {"c": {"check_x"}})
    other = _sweep("B", {"c": {"check_y"}})
    report = ad.compare([(ref, ref), (other, other)])
    assert not report.clean
    assert report.order_dependent[0].per_order == {"A": ["check_x"], "B": ["check_y"]}
    assert "check_x" in report.order_dependent[0].render()
    assert "check_y" in report.order_dependent[0].render()


def test_a_claim_that_vanishes_under_another_order_is_drift_not_absence() -> None:
    """`<nobody>` is rendered explicitly: a claim nobody made is still a move."""
    a = _sweep("A", {"c": {"check_x"}})
    b = _sweep("B", {})
    report = ad.compare([(a, a), (b, b)])
    assert not report.clean
    assert "<nobody>" in report.order_dependent[0].render()
