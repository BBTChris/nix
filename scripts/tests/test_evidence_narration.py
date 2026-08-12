"""ARC 027 (B3) — CHECK-DEBT D3.21's CLASS, swept and held, not patched once.

D3.21 is not "an unread number". It is **narration decoupled from measurement**:
an evidence/detail string authored independently of the thing it describes, so a
*correct verdict ships beside false evidence* and an operator reading the two
lines together concludes the opposite of the truth.

The canonical instance was `check_datafeed_bar_seal._drive_seal`, which appended
an equality defect and then returned a fixed note saying `"value equality holds"`
on the very same path.

## The four instances this arc found, and what each one is

Found by sweeping every `checks/check_*.py` (21) and every `scripts/nixverify/*.py`
(12) with four AST passes: constants appended to narration lists; `evidence=` /
`detail=` kwargs on `CheckResult`; `return <mutated-defect-list>, <literal>`; and
defect-reason literals carrying a digit that is not interpolated.

| site | sub-class | repaired by |
|---|---|---|
| `check_datafeed_bar_seal._drive_seal` | narration on a path where a
  defect was appended and NOT returned | one `equality_holds` name, read
  by both the defect and the note |
| `nixverify.actuation.session_state` | a SWALLOWED measurement narrated
  as `"(measured, not assumed)"` | the swallow records the unit; the
  verdict becomes `unknown` |
| `check_capture_plane2._arm_roundtrip` | a hardcoded count inside a
  sentence | `EXPECTED_MOVES` hoisted; the produced count passed in |
| `check_state_bus._arm_control` | the test read one counter, the
  sentence claimed another | both counters tested and narrated |

`actuation.session_state` is the worst of the four **by consequence rather than by
subtlety**: `SessionState.permits_mutation` is true only for `"inactive"`, so a
unit whose `systemctl show` never ran opened the trading-session interlock and let
`--correct`/`--install` proceed, carrying a parenthetical asserting the
measurement that had just been swallowed.

## CAN A GATE HOLD THIS CLASS CLOSED? Partly, and the boundary is measured here

**No,** in general. Deciding whether the English sentence *"value equality holds"*
is entailed by the code that emitted it requires knowing what the sentence means.
Three of the four instances above are invisible to any syntactic rule, and that is
not a limitation of this sweep but of the question:

* `actuation.session_state` has **no defect collection at all**. Its narration is
  a plain return value, and nothing syntactic distinguishes a true parenthetical
  from a false one.
* `_arm_roundtrip`'s `3` was a well-formed integer literal in a correct sentence.
  Every check in this tree contains integer literals in sentences.
* `_arm_control`'s test read `control["received"]` and its sentence claimed
  `control["bytes"]`. Both names exist, both are ints, both are in scope. Only the
  meaning of "bytes" tells them apart.

**And no for the fourth either, on measured numbers rather than on principle.**
The strongest decidable approximation — *a narration emitted on a path where a
defect was appended and not returned* — was built (`narration_defects`), run over
the real population, and REFUSED: it fires on many times more sites than the
reviewed defect population (overwhelmingly the per-item loop shape, which is
correct code), **and it still fires on `_drive_seal` after the repair**, because
the repair changed the data flow and left the control flow alone. A rule that
cannot tell the defect from its own fix does not encode the property.

So B3 ships FOUR REPAIRS, each with its own can-fail, plus this enumerator banked
runnable — and NO standing gate. `test_the_DECIDABLE_RULE_IS_NOT_SHIPPED_AS_A_GATE`
re-measures the refusal on every run, so if the rule ever becomes precise the
question re-opens loudly instead of being forgotten. Residual: CHECK-DEBT D3.31.

## debug.md §7.12 — the standing question

**What would have to be true for this sweep to pass while measuring nothing?**

1. **The file set could be empty** — a bad glob, a wrong root, a rename. Then
   "zero candidates, zero defects, PASS". *Closed:* `test_NONVACUITY_...` asserts
   the sweep parses at least `MIN_FILES` files and finds at least
   `MIN_FUNCTIONS_WITH_DEFECTS` functions that append to a defect collection —
   the population the rule is even capable of judging.
2. **The rule could be unable to fire at all** — a predicate that returns `[]` for
   every input passes over any population. *Closed:* `test_PLANT_...` feeds the
   rule the exact pre-repair `_drive_seal` shape and requires it to fire, naming
   the function.
3. **The rule could fire on everything**, which is the same as firing on nothing.
   *Not closed — MEASURED, and it is why no gate ships.* `test_CONTROL_...` shows
   the rule is silent on two correct shapes, and
   `test_the_DECIDABLE_RULE_IS_NOT_SHIPPED_AS_A_GATE` shows it is nonetheless far
   too broad on the real tree. The instrument reports its own unfitness rather
   than being switched on and suppressed.
4. **The repairs could be reverted without this file noticing**, because the rule
   only sees one of the four sub-classes. *Closed:* each of the other three
   repairs has its own direct assertion below, on the site rather than on the
   class.
"""
# pylint: disable=invalid-name,import-outside-toplevel,duplicate-code

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.append(str(REPO / "checks"))

#: Names this tree uses for a collection of `(site, why)` defects. Read off the
#: population rather than invented: every check that accumulates defects uses one
#: of these, and `test_NONVACUITY_...` asserts the vocabulary still matches enough
#: real functions to be worth applying.
DEFECT_NAMES = frozenset({"defects", "problems", "violations", "failures"})

#: Names this tree uses for the narration a check hands back beside its verdict.
NARRATION_NAMES = frozenset({"ev", "evidence", "notes", "advisories"})

#: Floors, so a sweep that stopped seeing the tree cannot report a clean result.
MIN_FILES = 25
MIN_FUNCTIONS_WITH_DEFECTS = 10


def _swept_files() -> list[Path]:
    """The population: every check and every nixverify module."""
    return sorted((REPO / "checks").glob("check_*.py")) + sorted(
        (REPO / "scripts" / "nixverify").glob("*.py")
    )


def _appends_to(node: ast.AST, names: frozenset[str]) -> set[str]:
    """Every name in `names` this subtree calls `.append(...)` on."""
    found: set[str] = set()
    for call in ast.walk(node):
        if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
            continue
        if call.func.attr not in ("append", "extend"):
            continue
        target = call.func.value
        if isinstance(target, ast.Name) and target.id in names:
            found.add(target.id)
    return found


def _exits(body: list[ast.stmt]) -> bool:
    """True when this block certainly leaves the function."""
    return bool(body) and isinstance(body[-1], (ast.Return, ast.Raise, ast.Continue))


def _is_narrating_return(stmt: ast.AST) -> bool:
    """`return <defects>, "..."` — the shape `_drive_seal` uses."""
    if not isinstance(stmt, ast.Return) or not isinstance(stmt.value, ast.Tuple):
        return False
    return any(_is_stringy(elt) for elt in stmt.value.elts)


def _is_narrating_append(stmt: ast.AST, defect_names: set[str]) -> bool:
    """`ev.append("...")` — the shape the arm functions use."""
    if not isinstance(stmt, ast.Expr) or not isinstance(stmt.value, ast.Call):
        return False
    call = stmt.value
    func = call.func
    if not isinstance(func, ast.Attribute) or func.attr != "append":
        return False
    target = func.value
    if not isinstance(target, ast.Name) or target.id not in NARRATION_NAMES:
        return False
    if target.id in defect_names or not call.args:
        return False
    return _is_stringy(call.args[0])


def _narrations(node: ast.AST, defect_names: set[str]) -> list[ast.AST]:
    """Statements that emit a narration string: a return-tuple or a note append."""
    return [
        stmt
        for stmt in ast.walk(node)
        if _is_narrating_return(stmt) or _is_narrating_append(stmt, defect_names)
    ]


def _is_stringy(node: ast.AST) -> bool:
    """A string literal or an f-string — the shapes a narration is written in."""
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str)
    if isinstance(node, ast.JoinedStr):
        return True
    if isinstance(node, ast.BinOp):
        return _is_stringy(node.left) or _is_stringy(node.right)
    return False


def narration_defects(tree: ast.Module, where: str) -> list[tuple[str, str]]:
    """Every narration emitted on a path where a defect was appended and NOT returned.

    THE DECIDABLE HALF OF D3.21's CLASS. The property is control flow, not
    meaning: if a function appends to its defect collection inside a branch that
    then falls through, any narration reached afterwards ships *beside a defect
    it does not know about*. Whether the sentence is true is undecidable; whether
    it was written without consulting the branch that just fired is not.

    A defect append is CLEARED when its enclosing block exits — `return`, `raise`
    or `continue` — because no narration in this function is then reachable from
    it. That single rule is what separates the canonical instance from the
    dozen functions in this tree that guard correctly by returning early.
    """
    defects: list[tuple[str, str]] = []
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        names = _appends_to(func, DEFECT_NAMES)
        if not names:
            continue
        falls_through = [
            block
            for block in ast.walk(func)
            if isinstance(block, (ast.If, ast.For, ast.While, ast.Try))
            and _appends_to_direct(block, names)
            and not _exits(block.body)
        ]
        if not falls_through:
            continue
        for stmt in _narrations(func, names):
            line = getattr(stmt, "lineno", 0)
            defects.append(
                (
                    f"{where}:{line} {func.name}",
                    (
                        f"a narration is emitted at line {line} on a path "
                        f"where {sorted(names)} was appended to at line(s) "
                        f"{sorted(block.lineno for block in falls_through)} without "
                        "leaving the function — the sentence cannot know whether "
                        "the defect fired (D3.21's class)"
                    ),
                )
            )
    return defects


def _appends_to_direct(block: ast.AST, names: set[str]) -> bool:
    """`block` appends to a defect name in its OWN body, not in a nested function."""
    body = getattr(block, "body", [])
    for stmt in body:
        for call in ast.walk(stmt):
            if isinstance(call, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and call.func.attr in ("append", "extend")
                and isinstance(call.func.value, ast.Name)
                and call.func.value.id in names
            ):
                return True
    return False


# --- NON-VACUITY, BEFORE ANY ASSERTION (doctrine C.3, §5.1 step 2) ----------


def test_NONVACUITY_the_sweep_reaches_a_real_population_it_can_judge() -> None:
    """A rule applied to nothing reports clean. Both floors are measured."""
    files = _swept_files()
    assert len(files) >= MIN_FILES, f"only {len(files)} file(s) swept: {files}"

    judgeable = 0
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for func in ast.walk(tree):
            if isinstance(
                func, (ast.FunctionDef, ast.AsyncFunctionDef)
            ) and _appends_to(func, DEFECT_NAMES):
                judgeable += 1
    assert judgeable >= MIN_FUNCTIONS_WITH_DEFECTS, (
        f"only {judgeable} function(s) in the whole population accumulate defects, "
        "so this rule has almost nothing to judge and a clean result means little"
    )


def test_PLANT_the_PRE_REPAIR_drive_seal_shape_FIRES_the_rule_naming_the_function() -> (
    None
):
    """*A rule that cannot fire passes over any population.*

    This is D3.21 verbatim: a defect appended in a branch that falls through, and
    a note returned afterwards asserting the opposite. If this stops firing, the
    rule has gone blind and every green below is worthless.
    """
    source = (
        "def _drive_seal(cls, plan, site):\n"
        "    defects = []\n"
        "    if first != same:\n"
        "        defects.append((site, 'compare UNEQUAL'))\n"
        "    try:\n"
        "        setattr(first, plan.vary, 1)\n"
        "    except AttributeError:\n"
        "        return defects, 'field write refused, value equality holds'\n"
        "    return defects, ''\n"
    )
    found = narration_defects(ast.parse(source), "PLANT")
    assert found, "the rule did not fire on the exact shape it exists to catch"
    assert any("_drive_seal" in site for site, _ in found), found
    assert any("cannot know whether the defect fired" in why for _, why in found)


def test_CONTROL_the_REPAIRED_shape_is_SILENT() -> None:
    """A rule that fires on everything is a rule nobody will leave switched on."""
    source = (
        "def _drive_seal(cls, plan, site):\n"
        "    defects = []\n"
        "    if not equality_holds:\n"
        "        defects.append((site, 'compare UNEQUAL'))\n"
        "        return defects, 'equality DOES NOT HOLD'\n"
        "    return defects, 'value equality holds'\n"
    )
    assert not narration_defects(ast.parse(source), "CONTROL")


def test_CONTROL_an_early_return_guard_is_NOT_flagged() -> None:
    """The `_arm_transitions` shape: append then return, then narrate. Correct."""
    source = (
        "def _arm(moves, defects, ev):\n"
        "    if moves != expected:\n"
        "        defects.append((site, 'wrong'))\n"
        "        return\n"
        "    ev.append('transitions ok')\n"
    )
    assert not narration_defects(ast.parse(source), "CONTROL")


def _population_hits() -> list[tuple[str, str]]:
    """The decidable rule, run over the whole swept population."""
    found: list[tuple[str, str]] = []
    for path in _swept_files():
        rel = path.relative_to(REPO)
        found.extend(
            narration_defects(
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path)),
                str(rel),
            )
        )
    return found


#: The reviewed true-positive population this arc found by reading, listed in the
#: module docstring's table. The number is the DENOMINATOR of the precision
#: measurement below; it is not a threshold and nothing is asserted equal to it.
REVIEWED_TRUE_POSITIVES = 4


def test_the_DECIDABLE_RULE_IS_NOT_SHIPPED_AS_A_GATE_and_here_is_the_measurement() -> (
    None
):
    """**Why B3 ships four repairs and an enumerator, and NO standing gate.**

    The brief asks whether a gate can hold this class closed. The control-flow
    rule above is the strongest decidable approximation available, and it was
    built, run over the real population, and REFUSED on its own numbers.

    Two measurements, both asserted here so the refusal is evidence rather than
    an opinion, and so it is re-measured on every pytest run:

    **1. PRECISION.** The rule fires on many times more sites than the reviewed
    defect population. Every extra hit is a correct function — overwhelmingly the
    per-item loop shape, where a note is appended for one item and a defect for a
    different one, on the same fall-through path. A gate at that precision is
    suppressed inside one arc, and a suppressed gate is furniture: it is the
    "rot into a suppression list" failure this project has already named twice.

    **2. AND IT CANNOT SEE ITS OWN REPAIR — which is decisive.** The rule still
    fires on `_drive_seal` AFTER the repair, because the repair changed the DATA
    FLOW (the sentence now reads `equality_holds`, the very name the defect
    condition tests) and left the CONTROL FLOW alone. A rule that cannot
    distinguish the defect from its fix does not encode the property. The
    property is *"does this sentence read the measurement it describes"*, which
    is data flow at best and meaning at worst — and no control-flow proxy
    reaches it.

    So the class is held by the four site repairs, each with its own can-fail
    below, and the residual is CHECK-DEBT D3.31 rather than a green nobody can
    trust.
    """
    hits = _population_hits()
    assert len(hits) > REVIEWED_TRUE_POSITIVES * 4, (
        "if the rule has become precise, re-open the question of shipping it as a "
        f"gate: {len(hits)} hit(s) against {REVIEWED_TRUE_POSITIVES} reviewed "
        "true positive(s)"
    )
    # The decisive one: the repaired canonical site is still flagged.
    assert any("check_datafeed_bar_seal.py" in site for site, _ in hits), (
        "the rule no longer fires on the REPAIRED _drive_seal — if that is because "
        "the rule learned data flow, it may be worth shipping after all"
    )


# --- THE THREE SUB-CLASSES THE RULE CANNOT SEE, ASSERTED AT THE SITE ---------


def test_REPAIR_the_bar_seal_note_is_DERIVED_from_the_equality_it_describes() -> None:
    """D3.21's own site: one name, read by both the defect and the sentence."""
    source = (REPO / "checks" / "check_datafeed_bar_seal.py").read_text(
        encoding="utf-8"
    )
    assert "equality_holds = first == same" in source, (
        "the note must be read off the same comparison the defect is"
    )
    assert "'holds' if equality_holds else 'DOES NOT HOLD'" in source, source[:0]
    assert "field write refused, value equality holds" not in source, (
        "the unconditional claim is back"
    )


def test_REPAIR_a_SWALLOWED_systemctl_probe_no_longer_reads_as_INACTIVE() -> None:
    """The safety one. `inactive` grants mutation; `unknown` withholds it.

    Driven rather than read: a `session_state` whose per-unit probe cannot run
    must not return the state that opens the trading-session interlock.
    """
    import subprocess

    from nixverify import actuation

    calls = {"n": 0}
    real = subprocess.run

    def _first_ok_then_broken(argv, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return real(argv, *args, **kwargs)  # pylint: disable=W1510
        raise OSError("systemctl show is unavailable")

    original = actuation.subprocess.run
    actuation.subprocess.run = _first_ok_then_broken  # type: ignore[assignment]
    try:
        state = actuation.session_state()
    finally:
        actuation.subprocess.run = original  # type: ignore[assignment]

    assert state.verdict != "inactive", (
        f"an UNMEASURED unit must never read as inactive — inactive is the state "
        f"that permits mutation: {state}"
    )
    assert not state.permits_mutation, state
    assert "UNMEASURED" in state.detail or "could not be probed" in state.detail, state
    assert "measured, not assumed" not in state.detail, (
        "the parenthetical that asserted the swallowed measurement is back"
    )


def test_REPAIR_the_plane2_roundtrip_count_is_no_longer_a_literal_in_a_sentence() -> (
    None
):
    """The expectation and the observation are now two named, derived values."""
    source = (REPO / "checks" / "check_capture_plane2.py").read_text(encoding="utf-8")
    assert "EXPECTED_MOVES" in source
    assert "the process emitted 3" not in source, "the hardcoded count is back"
    assert "the process produced {produced}" in source


def test_REPAIR_the_state_bus_control_tests_the_counter_its_sentence_claims() -> None:
    """`bytes_received` moves before `_decode`; `received` only after it."""
    source = (REPO / "checks" / "check_state_bus.py").read_text(encoding="utf-8")
    assert 'if control["received"] or control["bytes"]:' in source, (
        "the control must test BOTH counters, since they can diverge"
    )
    assert "late subscriber received 0 bytes" not in source, (
        "the unconditional zero is back"
    )
