"""ARC 024 §3.4/§3.5 — `--optimize` derives a plan and fails loud on four things.

§3.5's four loud failures each get a test that shows the failure FIRING, not a
test that shows the happy path and trusts the rest. The `trading-stack`
measurement at the bottom is the §0b refusal's acceptance test: it is the reason
this repo's existing multi-check blocks were NOT promoted to parallel.
"""
# pylint: disable=invalid-name,import-outside-toplevel,use-implicit-booleaness-not-comparison
# Test names SHOUT the property under test on purpose; `== ()` is asserted
# rather than `not x` because an empty tuple and a falsey non-tuple are
# different outcomes here; late imports are the sys.path bootstrap this suite
# needs. Each is deliberate, so the pragma is per-file and named.

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import verify  # pylint: disable=wrong-import-position
from nixverify.declarations import read_all  # pylint: disable=wrong-import-position
from nixverify.optimize import (  # pylint: disable=wrong-import-position
    derive_plan,
    plan_to_payload,
)


def _check(tmp_path: Path, name: str, depends: str, resources: str) -> None:
    (tmp_path / f"{name}.py").write_text(
        f"DEPENDS_ON = {depends}\nRESOURCES = {resources}\n", encoding="utf-8"
    )


def _registry(tmp_path: Path, names: list[str]) -> Path:
    path = tmp_path / "registry.json"
    path.write_text(
        json.dumps({"blocks": [{"name": "all", "checks": names}]}), encoding="utf-8"
    )
    return path


def test_derives_levels_least_dependent_first(tmp_path: Path) -> None:
    """The ordering invariant: everything at level n depends only on levels < n."""
    _check(tmp_path, "check_a", "()", "()")
    _check(tmp_path, "check_b", "('check_a',)", "()")
    _check(tmp_path, "check_c", "('check_b',)", "()")
    plan = derive_plan(tmp_path, _registry(tmp_path, ["check_a", "check_b", "check_c"]))
    assert plan.ok, plan.errors
    assert [b.checks for b in plan.blocks] == [
        ("check_a",),
        ("check_b",),
        ("check_c",),
    ]


def test_a_level_with_disjoint_claims_becomes_a_PARALLEL_block(tmp_path: Path) -> None:
    """Parallelism is granted on proven disjointness, not on 'by definition'."""
    _check(tmp_path, "check_a", "()", "('journal',)")
    _check(tmp_path, "check_b", "()", "('port:5432',)")
    plan = derive_plan(tmp_path, _registry(tmp_path, ["check_a", "check_b"]))
    assert plan.ok, plan.errors
    assert len(plan.blocks) == 1
    assert plan.blocks[0].parallel is True
    assert set(plan.blocks[0].checks) == {"check_a", "check_b"}


def test_LOUD_FAILURE_1_a_cycle_names_its_participants(tmp_path: Path) -> None:
    """§3.5: a cycle is an error naming the checks; never a silently chosen order."""
    _check(tmp_path, "check_a", "('check_b',)", "()")
    _check(tmp_path, "check_b", "('check_a',)", "()")
    plan = derive_plan(tmp_path, _registry(tmp_path, ["check_a", "check_b"]))
    assert not plan.ok
    cycle = [e for e in plan.errors if "CYCLE" in e]
    assert cycle, plan.errors
    assert "check_a" in cycle[0] and "check_b" in cycle[0]


def test_LOUD_FAILURE_2_an_orphan_is_reported_in_both_directions(
    tmp_path: Path,
) -> None:
    """A file with no registry entry, and a registry entry with no file.

    Only the folder-derived direction can see the first, which is why the plan
    is derived from the folder. This is the fifth instance of the project's
    tracking-state-sets-gate-scope defect class.
    """
    _check(tmp_path, "check_present", "()", "()")
    _check(tmp_path, "check_orphan", "()", "()")
    registry = _registry(tmp_path, ["check_present", "check_ghost"])
    plan = derive_plan(tmp_path, registry)
    assert not plan.ok
    assert any("check_orphan" in e and "ORPHAN" in e for e in plan.errors), plan.errors
    assert any("check_ghost" in e and "no file" in e for e in plan.errors), plan.errors


def test_LOUD_FAILURE_3_an_undeclared_check_cannot_be_placed(tmp_path: Path) -> None:
    """A check that declares nothing is an error, never a default of 'no deps'."""
    (tmp_path / "check_mute.py").write_text("X = 1\n", encoding="utf-8")
    plan = derive_plan(tmp_path, _registry(tmp_path, ["check_mute"]))
    assert not plan.ok
    assert any("declares no DEPENDS_ON" in e for e in plan.errors), plan.errors


def test_LOUD_FAILURE_4_a_non_disjoint_level_does_not_go_parallel(
    tmp_path: Path,
) -> None:
    """§3.2: shared claims force sequential execution, and the reason is reported.

    Note this is a NOTE, not an error: a level that cannot go parallel is still
    perfectly runnable in sequence, and refusing to emit a plan over it would
    make the safe outcome the unavailable one.
    """
    _check(tmp_path, "check_a", "()", "('port:4002',)")
    _check(tmp_path, "check_b", "()", "('port:4002',)")
    plan = derive_plan(tmp_path, _registry(tmp_path, ["check_a", "check_b"]))
    assert plan.ok, plan.errors
    assert plan.blocks[0].parallel is False
    assert any("not disjoint" in n and "port:4002" in n for n in plan.notes), plan.notes


def test_an_UNDECLARED_member_blocks_parallelism_even_beside_declared_ones(
    tmp_path: Path,
) -> None:
    """The §0a hole in 3.2, closed.

    3.5 makes *declaring nothing* loud. It says nothing about a check that
    declares no RESOURCES while its neighbour declares some — and "unknown
    claims" must never be optimistically read as "no claims".
    """
    (tmp_path / "check_known.py").write_text(
        "DEPENDS_ON = ()\nRESOURCES = ('journal',)\n", encoding="utf-8"
    )
    (tmp_path / "check_unknown.py").write_text("DEPENDS_ON = ()\n", encoding="utf-8")
    plan = derive_plan(tmp_path, _registry(tmp_path, ["check_known", "check_unknown"]))
    assert plan.blocks[0].parallel is False
    assert any("declares no RESOURCES" in n for n in plan.notes), plan.notes


def test_a_dependency_on_a_nonexistent_check_is_named(tmp_path: Path) -> None:
    """A typo'd dependency must not silently become a root-level check."""
    _check(tmp_path, "check_a", "('check_nope',)", "()")
    plan = derive_plan(tmp_path, _registry(tmp_path, ["check_a"]))
    assert not plan.ok
    assert any("check_nope" in e for e in plan.errors), plan.errors


def test_optimize_PROPOSES_and_does_not_overwrite(tmp_path: Path) -> None:
    """[ARCHITECT RULING — revocable] propose-then-commit, not overwrite.

    The live manifest must be byte-identical after `--optimize` without
    `--commit`.
    """
    _check(tmp_path, "check_a", "()", "('journal',)")
    registry = _registry(tmp_path, ["check_a"])
    before = registry.read_text(encoding="utf-8")
    code = verify.main(["--optimize", "--manifest", str(registry)])
    assert code == 0
    assert registry.read_text(encoding="utf-8") == before, "the live manifest moved"
    proposed = tmp_path / "registry.json.proposed"
    assert proposed.is_file()
    assert (
        "check_a"
        in json.loads(proposed.read_text(encoding="utf-8"))["blocks"][0]["checks"]
    )


def test_optimize_with_commit_installs_the_plan(tmp_path: Path) -> None:
    """`--commit` restores the operator's ruling exactly."""
    _check(tmp_path, "check_a", "()", "('journal',)")
    registry = _registry(tmp_path, ["check_a"])
    assert verify.main(["--optimize", "--commit", "--manifest", str(registry)]) == 0
    payload = json.loads(registry.read_text(encoding="utf-8"))
    assert payload["blocks"][0]["checks"] == ["check_a"]
    assert "DERIVED by `verify.py --optimize`" in payload["comment"]


def test_a_failed_derivation_writes_NOTHING(tmp_path: Path) -> None:
    """Fail closed: not even a .proposed file.

    A `.proposed` on disk is an invitation to commit it, and a plan with a cycle
    must not be one keystroke away from being installed.
    """
    _check(tmp_path, "check_a", "('check_b',)", "()")
    _check(tmp_path, "check_b", "('check_a',)", "()")
    registry = _registry(tmp_path, ["check_a", "check_b"])
    before = registry.read_text(encoding="utf-8")
    assert verify.main(["--optimize", "--manifest", str(registry)]) == 1
    assert registry.read_text(encoding="utf-8") == before
    assert not (tmp_path / "registry.json.proposed").exists()


def test_payload_records_each_blocks_claims(tmp_path: Path) -> None:
    """The derived manifest carries the claims the parallel decision rested on."""
    _check(tmp_path, "check_a", "()", "('journal',)")
    _check(tmp_path, "check_b", "()", "('port:5432',)")
    plan = derive_plan(tmp_path, _registry(tmp_path, ["check_a", "check_b"]))
    payload = plan_to_payload(plan, read_all(tmp_path))
    assert payload["blocks"][0]["claims"] == ["journal", "port:5432"]


def test_the_two_gateway_gates_share_an_endpoint_and_must_not_go_parallel() -> None:
    """§0b REFUSAL, banked as a test.

    ARC 024 measured both `check_ibgateway_config` and `check_ibgateway_service`
    dialling `('127.0.0.1', 4002)`, and they sit in the same registry block
    (`trading-stack`). Stage 3.1 as written — *a block containing multiple
    checks runs those in parallel, and by definition they have no dependency on
    one another* — would promote that block and put two checks concurrently on
    the same IBKR API port. clientId 1/2/905 are distinct precisely because IBKR
    sessions collide.

    **The hazard is currently MASKED, which is what makes it dangerous.** The
    Gateway is down, so both gates get ECONNREFUSED and a parallel promotion
    would look harmless today and fail intermittently once the Gateway is up —
    reading as a network problem, not a tooling one.

    This test pins the refusal: while either gate declares no RESOURCES, the
    block stays sequential. When they do declare, they will declare the same
    endpoint and the disjointness rule keeps them sequential on its own.
    """
    declarations = read_all(REPO / "checks")
    for name in ("check_ibgateway_config", "check_ibgateway_service"):
        assert name in declarations
    registry = json.loads(
        (REPO / "checks" / "registry.json").read_text(encoding="utf-8")
    )
    shared_block = [
        block
        for block in registry["blocks"]
        if {"check_ibgateway_config", "check_ibgateway_service"} <= set(block["checks"])
    ]
    assert shared_block, "the two Gateway gates are expected to share a block"
    assert shared_block[0].get("parallel", False) is False, (
        "the block holding both Gateway gates must not be parallel — they were "
        "measured dialling the same endpoint 127.0.0.1:4002"
    )
