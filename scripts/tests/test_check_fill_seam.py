"""ARC 034 / 0.6 — the can-fail suite for the fill-handler seam gate.

Structure follows `nix_check_contract.md` §5.1: non-vacuity FIRST, then one plant
per DECLARED PROPERTY that must FAIL and NAME its site, then the plants removed
and the same population passing. A demonstration missing the last step shows only
that a gate can fail.

**No plant touches a production artifact** (doctrine C.8, CHECK-DEBT D3.189).
Every can-fail builds a throwaway `nix_home` under `tmp_path` holding COPIES of
`scripts/nixrisk/fill_seam.py` and the collaborators the gate imports, perturbs
the COPY, and drives the SHIPPED gate's own bytes against it. The real
`scripts/nixrisk/fill_seam.py` and the real `scripts/nixrisk/seam.py` are read
and never written — a test that transiently edits a production module leaves
residue indistinguishable from a real defect when the run is killed.

**THE PLANT THAT MATTERS MOST is `test_a_DRIFTED_PARAMETER_NAME_reddens...`.**
It renames one parameter of `StopArmPort.arm` and changes nothing else. The
`runtime_checkable` `isinstance` still returns `True` — that call compares METHOD
NAMES ONLY and is blind to arity, to parameter names and to every annotation —
so a gate resting on `isinstance` alone would be green over a port no caller can
actually use. That exact weakness was measured in ARC 033's gates, and this
control is what proves ARM 5 is more than a name check.

**Every control asserts the REASON** — a substring of `site` or `detail` naming
WHAT was wrong — never the status alone (check contract v2 §11 / §18).
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# Test names SHOUT the property; the sys.path bootstrap is identical in every
# check test by requirement.

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
# APPENDED, never inserted at the front — loader.py's failure mode #8 note.
sys.path.append(str(REPO / "checks"))

import check_fill_seam as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)

#: Everything the gate reads or imports, copied into the throwaway tree. ARM 5
#: constructs `StopBook` and `PositionOriginWriter` for real, so their whole
#: import closure has to be here — a partial copy would make every red below an
#: ImportError rather than a measurement.
_COPIED = (
    "scripts/nixrisk/__init__.py",
    "scripts/nixrisk/seam.py",
    "scripts/nixrisk/picture.py",
    "scripts/nixrisk/execution.py",
    "scripts/nixrisk/stops.py",
    "scripts/nixrisk/positions.py",
    gate.SEAM,
)

#: The seam's `StopArmPort.arm` declaration, used as an anchor by three plants.
_ARM_DECL = "    def arm(self, fill_price: float, order: ProposedOrder) -> StopState:"
_ARM_DOC = (
    '        """Convert the order\'s tick distance to an absolute price, '
    'ONCE (§4)."""\n'
)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """A throwaway tree carrying COPIES of the seam and its import closure."""
    (tmp_path / "scripts" / "nixrisk").mkdir(parents=True)
    for rel in _COPIED:
        shutil.copy(REPO / rel, tmp_path / rel)
    return tmp_path


def _run(nix_home: Path):
    return gate.run(Mode.VERIFY, Context(nix_home=nix_home, mode=Mode.VERIFY))


def _plant(home: Path, old: str, new: str, *, rel: str | None = None) -> None:
    """Perturb the COPY, asserting the anchor really was there.

    The assertion is the load-bearing half: a plant whose anchor has drifted
    silently mutates nothing, the gate stays green, and the control reports that
    the gate reddens on a change it never saw — a suite measuring itself.
    """
    path = home / (rel or gate.SEAM)
    source = path.read_text(encoding="utf-8")
    assert old in source, f"the plant anchor {old!r} is not in {rel or gate.SEAM}"
    path.write_text(source.replace(old, new, 1), encoding="utf-8")


# --------------------------------------------------------------------------
# NON-VACUITY FIRST — the gate reaches a real reference side and a real subject
# --------------------------------------------------------------------------


def test_the_REAL_TREE_passes_and_the_EVIDENCE_names_what_was_MEASURED() -> None:
    """The credibility floor: the figures are in evidence, not a restatement."""
    result = _run(REPO)

    assert result.status is Status.PASS, result
    assert "ARM_STOP=1, RELEASE_REMAINDER=2, ORIGIN_WRITE=3" in result.evidence, (
        result.evidence
    )
    assert "6 callable(s) classified" in result.evidence, result.evidence
    assert "2 class->port pair(s) DRIVEN" in result.evidence, result.evidence
    assert "StopBook->StopArmPort" in result.evidence, result.evidence


def test_the_STEP_ORDER_is_PARSED_FROM_THE_SEAM_and_is_not_a_constant_here() -> None:
    """If the expected order were hardcoded, reordering the list could not move it."""
    source = (REPO / gate.SEAM).read_text(encoding="utf-8")

    assert gate.declared_step_order(source) == (
        "ARM_STOP",
        "RELEASE_REMAINDER",
        "ORIGIN_WRITE",
    )
    gate_source = Path(gate.__file__).read_text(encoding="utf-8")
    for member in ("ARM_STOP", "RELEASE_REMAINDER", "ORIGIN_WRITE"):
        assert f'"{member}"' not in gate_source, (
            f"{member} appears as a string literal in the gate's own source — "
            "the expected order would then be a constant, and ARM 1 would be the "
            "gate agreeing with itself"
        )


def test_ARM_4s_REFERENCE_ROSTER_comes_from_a_DIFFERENT_FILE() -> None:
    """The narrowing is measured against `nixrisk/seam.py`, never against itself.

    A roster read out of the subject would let the subject widen itself into
    agreement — §7.12 note 3, and the failure `check_pollers` ARM LOCK was
    measured committing in ARC 034 / 0.5.
    """
    import ast  # pylint: disable=import-outside-toplevel

    tree = ast.parse((REPO / gate.STOP_SEAM).read_text(encoding="utf-8"))

    assert gate.stopbook_verbs(tree) == ("arm", "maintain", "breached", "forget")
    gate_source = Path(gate.__file__).read_text(encoding="utf-8")
    for verb in ("maintain", "breached"):
        assert f'"{verb}"' not in gate_source, (
            f"{verb} appears as a string literal in the gate's own source — the "
            "reference roster would then be a constant here rather than a read "
            "of the frozen seam"
        )


def test_the_GATE_DECLARES_the_seam_as_a_SUBJECT_so_coverage_is_real() -> None:
    """The coverage ratchet reads SUBJECTS; a gate that measures without
    declaring leaves its artifact looking uncovered, and one that declares
    without measuring is the suppression file the ratchet exists to prevent."""
    assert gate.SEAM in gate.SUBJECTS, gate.SUBJECTS
    assert gate.CORRECTABLE is False
    assert gate.NON_CORRECTABLE_REASON, "a refusal must carry its reason"


def test_EVERY_DECLARED_FLOOR_IS_STRICTLY_BELOW_TODAYS_FIGURE() -> None:
    """ARC 034 / 0.5 measured five of ARC 033's floors being identities.

    A floor at or above today's figure reddens on the next edit and discriminates
    nothing before then (doctrine C.4); a floor of zero discriminates nothing
    ever. This control holds every floor in the gate against what the real tree
    actually carries, so a floor written as `300 < 100` cannot ship again.
    """
    result = _run(REPO)
    assert result.status is Status.PASS, result

    today = {
        gate.MIN_ORDERED_STEPS: 3,
        gate.MIN_CALLABLES: 6,
        gate.MIN_DECLARED_VERBS: 6,
        gate.MIN_PORTS: 6,
        gate.MIN_STOPBOOK_VERBS: 4,
    }
    for floor, observed in today.items():
        assert 0 < floor < observed, (
            f"floor {floor} against an observed {observed} is not a floor below "
            "today's figure and non-zero"
        )
    # And the observed figures really are what the evidence reported, so the
    # right-hand side above is a measurement rather than a second constant.
    assert "3 step(s)" in result.evidence, result.evidence
    assert "6 callable(s) classified, 6 declared verb(s)" in result.evidence
    assert "6 Protocol port(s)" in result.evidence, result.evidence
    assert "arm, maintain, breached, forget" in result.evidence, result.evidence


# --------------------------------------------------------------------------
# ARM 1 — THE STEP ORDER. Three plants, one per way the order can be lost.
# --------------------------------------------------------------------------


def test_REORDERED_FillStep_VALUES_redden_and_NAME_the_member(home: Path) -> None:
    """The VALUES are the order, so moving one is moving the safety property.

    §4 requires the stop ARMED before §3's row is written:
    `PositionOriginWriter.on_fill` refuses an unstopped fill, and a defaulted
    zero distance would price a real position at zero dollar risk, make the
    correlation bucket read emptier than it is and ADMIT MORE (§7:501).
    """
    _plant(home, "    ORIGIN_WRITE = 3\n", "    ORIGIN_WRITE = 0\n")

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "FillStep" in result.site, result.site
    assert "ORIGIN_WRITE=0" in result.detail, result.detail
    assert "not strictly increasing" in result.detail, result.detail


def test_FillStep_DEMOTED_from_IntEnum_reddens_and_SAYS_SO(home: Path) -> None:
    """`IntEnum`, not `Enum`, is a declared property with a stated purpose.

    Over an `IntEnum` a later gate can assert `observed == sorted(observed)` on
    the steps a handler REALLY recorded. Over a plain `Enum` that comparison does
    not typecheck, and the order goes back to being asserted from source order —
    which proves nothing about execution order.
    """
    _plant(home, "class FillStep(enum.IntEnum):", "class FillStep(enum.Enum):")

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "FillStep" in result.site, result.site
    assert "not an `enum.IntEnum`" in result.detail, result.detail
    assert "sorted(observed)" in result.detail, result.detail


def test_a_DROPPED_FillStep_MEMBER_reddens_and_NAMES_the_member(home: Path) -> None:
    """A step the declaration names and the enum has lost.

    §4's partial-fill release sits BETWEEN the arm and the write for a stated
    reason: releasing after the write would publish a snapshot in which the
    over-reserved capital is still taken. A handler that skipped a step nothing
    can record would leave no observable trace.
    """
    _plant(home, "    RELEASE_REMAINDER = 2\n", "")

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "FillStep.RELEASE_REMAINDER" in result.site, result.site
    assert "has no such member" in result.detail, result.detail


# --------------------------------------------------------------------------
# ARM 2 — SYNCHRONY
# --------------------------------------------------------------------------


def test_an_ASYNC_VERB_reddens_and_NAMES_the_verb_and_the_TEAR(home: Path) -> None:
    """§5's single-threaded loop and §3's atomicity rule, held as a property.

    `on_fill` performs FOUR state changes §3 and §4 require to be one motion. An
    `async def` anywhere in that sequence is a declared suspension point, and the
    loop servicing a second fill inside it would publish a snapshot from between
    two halves of one fill.
    """
    _plant(home, "    def release_remainder(\n", "    async def release_remainder(\n")

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "release_remainder" in result.site, result.site
    assert "is `async def`" in result.detail, result.detail
    assert "fill-vs-tick races" in result.detail, result.detail


# --------------------------------------------------------------------------
# ARM 3 — NO BEHAVIOUR, and the first-party imports that must stay legal
# --------------------------------------------------------------------------


def test_BEHAVIOUR_IN_THE_SEAM_reddens_and_NAMES_THE_MODULE(home: Path) -> None:
    """An import that reaches the world is enough — a seam declares and acts not."""
    _plant(home, "import enum\n", "import enum\nimport os\n")

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "imports os" in result.detail, result.detail
    assert "does not act" in result.detail, result.detail


def test_BEHAVIOUR_INSIDE_A_PORT_METHOD_reddens_and_NAMES_the_verb(
    home: Path,
) -> None:
    """The half an import ban cannot reach: a statement in a Protocol body.

    A `raise NotImplementedError` needs no forbidden import and calls no
    forbidden builtin, and it reads as defensive good practice. It is still
    behaviour in a declaration, and a seam that carries behaviour is a second
    authority that can silently disagree with the spec.
    """
    _plant(
        home,
        '        """The approved order, or `None` if this Limiter never '
        'approved it."""\n',
        '        """The approved order, or `None` if this Limiter never '
        'approved it."""\n        raise NotImplementedError\n',
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "order_for" in result.site + result.detail, (result.site, result.detail)
    assert "behaviour, not a declaration" in result.detail, result.detail


def test_the_SEAMS_OWN_FIRST_PARTY_IMPORTS_are_NOT_a_defect() -> None:
    """The other half of ARM 3, and the reason the roster is narrowed.

    `fill_seam.py` imports `nixrisk.execution`, `nixrisk.positions` and
    `nixrisk.seam` to spell the types its ports take and return. A roster that
    banned them would force those annotations into strings — trading a real
    property (the seam touches nothing) for a false one (the seam may not NAME
    the types it declares over). This asserts the narrowing is REAL rather than
    an unexercised comment: the real tree carries all three imports and passes.
    """
    source = (REPO / gate.SEAM).read_text(encoding="utf-8")

    assert "from nixrisk.execution import" in source
    assert "from nixrisk.positions import" in source
    assert "from nixrisk.seam import" in source
    assert _run(REPO).status is Status.PASS


# --------------------------------------------------------------------------
# ARM 4 — THE NARROWING
# --------------------------------------------------------------------------


def test_StopArmPort_GAINING_forget_reddens_and_NAMES_the_verb(home: Path) -> None:
    """The narrowing is how the authority boundary stops being a convention.

    `forget` is still a member of `StopBookPort`, so a bare proper-subset test
    would stay green — the widened port is a subset of the book right up until it
    is the whole book. The cardinality rule is what catches it: the fill handler
    consumes exactly ONE verb, and per-tick maintenance and stop-out detection
    belong to the tick path.
    """
    _plant(
        home,
        _ARM_DECL + "\n" + _ARM_DOC,
        _ARM_DECL
        + "\n"
        + _ARM_DOC
        + "\n"
        + "    def forget(self, client_order_id: str) -> None:\n"
        + '        """Not the fill handler\'s authority."""\n',
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "StopArmPort" in result.site, result.site
    assert "arm, forget" in result.detail, result.detail
    assert "declares 2 verb(s)" in result.detail, result.detail
    assert "fire an exit from inside a fill" in result.detail, result.detail


def test_StopArmPort_GAINING_a_VERB_THE_BOOK_LACKS_reddens_as_NOT_A_SUBSET(
    home: Path,
) -> None:
    """The other failure direction: not narrower, just different.

    A port that is not even a SUBSET of the book it claims to narrow is a new
    surface wearing a narrowing's name, and no class satisfying the book need
    satisfy it.
    """
    _plant(
        home,
        _ARM_DECL + "\n" + _ARM_DOC,
        _ARM_DECL
        + "\n"
        + _ARM_DOC
        + "\n"
        + "    def rearm_at(self, price: float) -> None:\n"
        + '        """A verb StopBookPort does not have."""\n',
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "StopArmPort" in result.site, result.site
    assert "rearm_at" in result.detail, result.detail
    assert "not even a SUBSET" in result.detail, result.detail


# --------------------------------------------------------------------------
# ARM 5 — STRUCTURAL CONFORMANCE, DRIVEN. The `isinstance` blind spot.
# --------------------------------------------------------------------------


def test_a_DRIFTED_PARAMETER_NAME_reddens_though_ISINSTANCE_STILL_PASSES(
    home: Path,
) -> None:
    """THE CONTROL THAT MAKES ARM 5 MORE THAN A NAME CHECK.

    `runtime_checkable` `isinstance` compares METHOD NAMES ONLY. Rename
    `fill_price` to `at_price` on the port and `StopBook` still satisfies it —
    the method `arm` is still there — while every caller holding only the port
    and passing `fill_price=` by keyword now raises `TypeError` at the call. ARC
    033's gates were measured resting on exactly this. The premise is asserted
    first, so a green here can never be read as "the drift was caught by
    isinstance after all".
    """
    _plant(
        home,
        "    def arm(self, fill_price: float, order: ProposedOrder) -> StopState:",
        "    def arm(self, at_price: float, order: ProposedOrder) -> StopState:",
    )

    # THE PREMISE, MEASURED: isinstance is still True over the mutated port.
    loaded, complaint = gate.load(home)
    assert complaint == "", complaint
    assert loaded is not None
    assert isinstance(
        loaded.stops.StopBook({"ESZ6": 0.25}), loaded.fill_seam.StopArmPort
    ), (
        "the premise failed: isinstance already caught the drift, so this control proves nothing"
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "StopArmPort.arm" in result.site, result.site
    assert "METHOD NAMES ONLY" in result.detail, result.detail
    assert "at_price" in result.detail and "fill_price" in result.detail, result.detail


def test_a_CLASS_THAT_LOSES_THE_PORTS_VERB_reddens_and_NAMES_IT(home: Path) -> None:
    """The half `isinstance` CAN see, driven so the arm is not only a signature test.

    The plant is in the production CLASS, not in the seam: renaming
    `PositionOriginWriter.on_fill` leaves the port declaring a verb no shipped
    class has, which is the drift the pairing exists to catch.
    """
    _plant(
        home,
        "    def on_fill(\n        self, report: ExecutionReport, *, "
        "sum_reservations: float | None = None\n    ) -> OriginWrite:",
        "    def handle_fill(\n        self, report: ExecutionReport, *, "
        "sum_reservations: float | None = None\n    ) -> OriginWrite:",
        rel="scripts/nixrisk/positions.py",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "OriginWritePort" in result.site, result.site
    assert "does NOT structurally satisfy" in result.detail, result.detail
    assert "on_fill" in result.detail, result.detail


# --------------------------------------------------------------------------
# ARM 6 — D3.177's RULE HAS A DECLARED HOME (and nothing more than that)
# --------------------------------------------------------------------------


def test_TURNING_OFF_the_NON_IDENTITY_MINT_RULE_reddens(home: Path) -> None:
    """The rule turned off here is the rule turned off everywhere that reads it.

    An identity mint is an equality that holds by construction, so no observation
    can contradict it and every round-trip gate over it passes on every input.
    """
    _plant(
        home,
        "NON_IDENTITY_MINT_REQUIRED = True",
        "NON_IDENTITY_MINT_REQUIRED = False",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "NON_IDENTITY_MINT_REQUIRED" in result.site, result.site
    assert "is False, not True" in result.detail, result.detail
    assert "holds by construction" in result.detail, result.detail


def test_a_MINT_PORT_WITHOUT_ITS_VERB_reddens(home: Path) -> None:
    """A port with no minting verb cannot be the injected policy."""
    _plant(
        home,
        "    def mint(self, order: ProposedOrder) -> str:",
        "    def make(self, order: ProposedOrder) -> str:",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "TradeIdMintPort.mint" in result.site, result.site
    assert "declares no 'mint' verb" in result.detail, result.detail


def test_ARM_6_DOES_NOT_CLAIM_THE_PRODUCTION_MINT_IS_NON_IDENTITY() -> None:
    """The stated limitation, asserted so a green cannot be over-read.

    `positions.identity_trade_id` returns `order.client_order_id` unchanged and
    is still on the tree. ARM 6 checks that D3.177's RULE has a declared home; it
    does not and cannot check any minting code, and the gate says so in its own
    evidence rather than leaving a reader to infer it.
    """
    result = _run(REPO)

    assert result.status is Status.PASS, result
    assert "never a statement about any production mint" in result.evidence, (
        result.evidence
    )
    assert "identity_trade_id" in (REPO / "scripts/nixrisk/positions.py").read_text(
        encoding="utf-8"
    ), (
        "the degenerate mint is gone, so this control's premise has changed and "
        "ARM 6's stated limitation needs re-reading"
    )


# --------------------------------------------------------------------------
# CANNOT_MEASURE, never PASS — an absent side is not agreement
# --------------------------------------------------------------------------


def test_a_RENAMED_STEP_LIST_is_CANNOT_MEASURE_and_NEVER_a_PASS(home: Path) -> None:
    """The floor working, and the vacuity that would matter most.

    ARM 1's expected ORDER is parsed from the seam's own numbered list. Rename
    that list and the order is empty — and "strictly increasing" over an empty
    sequence is true of every possible enum, including one with no members.
    """
    seam = home / gate.SEAM
    source = seam.read_text(encoding="utf-8")
    for rank in ("1", "2", "3"):
        assert f"{rank}. `FillStep." in source, source[:200]
        source = source.replace(f"{rank}. `FillStep.", f"{rank}. `Phase.")
    seam.write_text(source, encoding="utf-8")

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "numbered step list yielded 0 step(s)" in result.detail, result.detail
    assert f"below the floor of {gate.MIN_ORDERED_STEPS}" in result.detail, (
        result.detail
    )
    assert result.site == "", (
        "a CANNOT_MEASURE carrying a site would mean the gate observed a defect "
        "and reported that it observed nothing"
    )


def test_an_ABSENT_SEAM_is_CANNOT_MEASURE_and_names_the_missing_path(
    home: Path,
) -> None:
    """A gate whose subject is gone measured nothing (§17)."""
    (home / gate.SEAM).unlink()

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert gate.SEAM in result.detail, result.detail
    assert "unreadable" in result.detail, result.detail


def test_an_ABSENT_REFERENCE_SEAM_is_CANNOT_MEASURE_not_a_free_narrowing(
    home: Path,
) -> None:
    """ARM 4's reference side gone must not read as a narrowing that holds."""
    (home / gate.STOP_SEAM).unlink()

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert gate.STOP_SEAM in result.detail, result.detail
    assert "reference roster is absent" in result.detail, result.detail


def test_a_TREE_WITHOUT_THE_PACKAGE_is_CANNOT_MEASURE_not_a_FALL_THROUGH(
    tmp_path: Path,
) -> None:
    """D3.124: `_preamble` appends the REAL `scripts/` and never removes it.

    An empty home must not resolve `nixrisk.fill_seam` against the live
    repository and report a PASS about a tree it never read.
    """
    result = _run(tmp_path)

    assert result.status is Status.CANNOT_MEASURE, result
    assert gate.SEAM in result.detail, result.detail


# --------------------------------------------------------------------------
# THE THIRD STEP — the plants removed, the same population passing
# --------------------------------------------------------------------------


def test_the_UNPLANTED_COPY_is_GREEN_so_every_RED_above_is_the_PLANT(
    home: Path,
) -> None:
    """The control without which every red above could be an artefact.

    A scratch tree assembled by this fixture could redden the gate all by itself
    — a missing collaborator, a mangled copy, a path the gate resolves
    differently — and then every plant above would be measuring the harness
    rather than the mutation. This is the same copied tree, unmutated.
    """
    result = _run(home)

    assert result.status is Status.PASS, result
    assert "2 class->port pair(s) DRIVEN" in result.evidence, result.evidence
