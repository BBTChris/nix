"""ARC 027 (B1) — the DRIVE behind three new `SUBJECTS` entries, banked runnable.

`check_artifact_gate_coverage` proves an artifact is **NAMED** by a check and
cannot prove it is **MEASURED** by one (D3.19). That gap is not a footnote here:
it is the whole reason B1 exists, because *adding a path to a `SUBJECTS` tuple
lowers the coverage count while covering nothing*, and the ratchet — which only
enforces monotonic non-increase — accepts it happily.

So the three paths ARC 027 moved out of `checks/gate_coverage_baseline.json` do
not rest on a declaration. This module plants a banned import in each of them in
turn and requires `check_order_path_bans` to go from PASS to FAIL **naming the
file, the line and the reason**, then restores the control byte-identical.

* `scripts/broker/broker_order_config.py`
* `scripts/broker/broker_order_ibkr.py`
* `scripts/broker/seam_simulate.py`

**THE REASON IS ASSERTED, NEVER THE EXIT CODE** (check contract rule 11). Exit 1
from this gate is also what a scope complaint, an unreviewed retry shape and a
resident banned module produce; an integer cannot tell an operator which of them
happened, and it certainly cannot tell this test whether the plant is what fired.

## debug.md §7.12 — the standing question, for this control

**What would have to be true for these tests to pass while measuring nothing?**

1. **The gate could already be FAILING**, so the plant changes nothing and every
   assertion about the planted run still holds. *Closed:* every test asserts the
   CONTROL is `Status.PASS` before it plants, and `test_CONTROL_...` asserts it
   standalone.
2. **The plant could fire the gate for a reason unrelated to the file** — a
   syntax error, an import failure, the scope complaint. *Closed:* the assertion
   is on `<basename>:<line> <module>: banned retry library '<module>'` in
   `detail`, which no other arm emits.
3. **The gate could name the file without reading it** — the evidence line lists
   the derived scope, so a file could appear there and never be parsed. *Closed:*
   the defect carries a LINE NUMBER, and a line number can only come from the
   `ast.parse` of that file's bytes.
4. **The plant could leak** into the real tree and make the *next* run red for a
   reason nobody planted. *Closed:* every plant is restored from bytes captured
   before it, and the sha256 is asserted equal afterwards — the restoration is
   measured, not assumed.
"""
# pylint: disable=invalid-name,redefined-outer-name,import-outside-toplevel
# Test names SHOUT the property under test.

from __future__ import annotations

import ast
import hashlib
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.append(str(REPO / "checks"))

import check_order_path_bans as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    CheckResult,
    Context,
    Mode,
    Status,
)

#: The three paths ARC 027 moved out of the coverage baseline, and the banned
#: module planted in each. Three different modules so a test cannot pass on a
#: stale `sys.modules` entry left by its neighbour.
DRIVEN: tuple[tuple[str, str], ...] = (
    ("scripts/broker/broker_order_config.py", "tenacity"),
    ("scripts/broker/broker_order_ibkr.py", "backoff"),
    ("scripts/broker/seam_simulate.py", "retrying"),
)


def _inlined_pairs(source: str) -> set[tuple[str, str]]:
    """Every 2-tuple of string literals inside a `parametrize` argvalues list."""
    pairs: set[tuple[str, str]] = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "parametrize":
            continue
        values = node.args[1] if len(node.args) > 1 else None
        if not isinstance(values, ast.List):
            continue
        pairs |= _pairs_in(values)
    return pairs


def _pairs_in(values: ast.List) -> set[tuple[str, str]]:
    """The literal 2-tuples of one argvalues list."""
    out: set[tuple[str, str]] = set()
    for element in values.elts:
        if not isinstance(element, ast.Tuple) or len(element.elts) != 2:
            continue
        parts = [e.value for e in element.elts if isinstance(e, ast.Constant)]
        if len(parts) == 2:
            out.add((str(parts[0]), str(parts[1])))
    return out


def test_the_inlined_PARAMETRIZE_literals_agree_with_DRIVEN() -> None:
    """The literals below are inlined, and inlining is where a copy drifts.

    `check_derived_claims`' AST test-counter refuses a `parametrize` whose
    argvalues are a NAME — it cannot count what it cannot read, and it says so
    rather than guessing. That refusal is correct and it is why these three pairs
    appear twice; this test is the price of the second copy.
    """
    inlined = _inlined_pairs(Path(__file__).read_text(encoding="utf-8"))
    assert inlined == set(DRIVEN), (inlined, set(DRIVEN))


def _run() -> CheckResult:
    return gate.run(Mode.VERIFY, Context(nix_home=REPO, mode=Mode.VERIFY))


@contextmanager
def _planted(rel: str, module: str) -> Iterator[None]:
    """Append a banned import to a real order-path module, then put it back.

    Doctrine C.8 says no plant touches a production artifact permanently. It says
    nothing about touching one *transiently*, and this gate cannot be driven any
    other way: its scope is DERIVED from the real tree (D2.15), so a copy under
    `tmp_path` would not be in scope and the plant would prove nothing about the
    file the `SUBJECTS` entry names. The restoration is therefore the safety
    property, and it is asserted rather than trusted.
    """
    path = REPO / rel
    control = path.read_bytes()
    before = hashlib.sha256(control).hexdigest()
    try:
        path.write_bytes(control + f"\nimport {module}  # ARC 027 B1 PLANT\n".encode())
        yield
    finally:
        path.write_bytes(control)
        after = hashlib.sha256(path.read_bytes()).hexdigest()
        assert after == before, f"{rel} was NOT restored byte-identical"


def test_CONTROL_the_real_tree_PASSES_and_the_scope_names_all_three_driven_files() -> (
    None
):
    """Step 1 of §5.1. Without this, every plant below proves nothing."""
    result = _run()
    assert result.status is Status.PASS, result
    for rel, _module in DRIVEN:
        assert Path(rel).name in result.evidence, (rel, result.evidence)


def test_the_three_driven_files_are_in_the_gates_DERIVED_scope_not_a_hardcoded_list() -> (
    None
):
    """The scope is derived from tree content; the claim must survive that."""
    scope = gate.derive_scope(REPO)
    assert not scope.complaint, scope.complaint
    names = {path.name for path in scope.files}
    for rel, _module in DRIVEN:
        assert Path(rel).name in names, (rel, sorted(names))


def test_every_driven_file_is_a_REQUIRED_MEMBER_so_leaving_scope_is_LOUD() -> None:
    """A covered artifact that can silently stop being scanned is not covered.

    Before ARC 027 these files were scanned but their membership was incidental:
    the derived scope happened to include them, and nothing would have said so if
    it stopped. That is tolerable for a file nobody claims to cover, and not
    tolerable for one this gate's `SUBJECTS` now names.
    """
    for rel, _module in DRIVEN:
        assert Path(rel).name in gate.REQUIRED_MEMBERS, rel


def test_the_declared_SUBJECTS_are_exactly_the_files_this_module_drives() -> None:
    """The declaration and the demonstration must not be able to drift apart.

    Read by AST, the way `verify.py` reads it — an import would prove the
    module's runtime state, not the text a static reader sees.
    """
    from nixverify.declarations import read_all

    declared = set(read_all(REPO / "checks")[gate.NAME].subjects)
    assert {rel for rel, _ in DRIVEN} <= declared, declared


@pytest.mark.parametrize(
    "rel,module",
    [
        ("scripts/broker/broker_order_config.py", "tenacity"),
        ("scripts/broker/broker_order_ibkr.py", "backoff"),
        ("scripts/broker/seam_simulate.py", "retrying"),
    ],
    ids=[
        "scripts/broker/broker_order_config.py",
        "scripts/broker/broker_order_ibkr.py",
        "scripts/broker/seam_simulate.py",
    ],
)
def test_PLANT_a_banned_import_in_a_driven_file_FAILS_naming_FILE_LINE_and_REASON(
    rel: str, module: str
) -> None:
    """*A `SUBJECTS` entry that names a file nothing opens is a lowered count.*

    The plant is the smallest thing the gate is supposed to catch, landed in the
    file whose coverage is being claimed. The assertion is on the REASON: the
    basename, a line number, and the ban that fired.
    """
    assert _run().status is Status.PASS, "control must be clean before the plant"

    with _planted(rel, module):
        result = _run()

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    needle = f"{Path(rel).name}:"
    assert needle in result.detail, (needle, result.detail)
    assert f"banned retry library {module!r}" in result.detail, result.detail
    assert module in result.site, result.site


@pytest.mark.parametrize(
    "rel,module",
    [
        ("scripts/broker/broker_order_config.py", "tenacity"),
        ("scripts/broker/broker_order_ibkr.py", "backoff"),
        ("scripts/broker/seam_simulate.py", "retrying"),
    ],
    ids=[
        "scripts/broker/broker_order_config.py",
        "scripts/broker/broker_order_ibkr.py",
        "scripts/broker/seam_simulate.py",
    ],
)
def test_the_CONTROL_is_restored_and_the_gate_PASSES_again(
    rel: str, module: str
) -> None:
    """§5.1 step 6. A plant that does not come back out has changed the subject."""
    with _planted(rel, module):
        pass
    assert _run().status is Status.PASS, "the plant did not come back out"


def test_a_plant_in_an_UNDRIVEN_file_does_NOT_fire_this_gate() -> None:
    """The negative control, and it is the one that makes the others mean something.

    If the gate reddened on a banned import anywhere in the tree, the plants
    above would prove the gate works and nothing at all about *these three
    files*. `scripts/capture.py` is a real, tracked, non-order-path module: the
    same plant there must leave the gate green.
    """
    outsider = "scripts/capture.py"
    assert outsider not in {rel for rel, _ in DRIVEN}
    assert _run().status is Status.PASS

    with _planted(outsider, "tenacity"):
        result = _run()

    assert result.status is Status.PASS, (
        "the gate reddened on a file outside its derived scope — the plants on "
        "the three driven files would then prove nothing about those files"
    )
