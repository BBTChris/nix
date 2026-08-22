"""ARC 058 — the can-fail suite for `checks/check_i1_convergence.py` (rule 4).

Non-vacuity FIRST (the REAL tree's own five vocabularies derive the real
required-path set and every member of it is judged INVOKED), then plants that
must turn the gate's own judgement RED and NAME the site, then the plants removed
and the same inputs judged clean again.

**No plant touches a production artifact** (doctrine C.8), and no plant copies
the tree. This gate SPAWNS six `limiterd` processes out of `nix_home`, so a
scratch `nix_home` built by copying `~/nix` under `tmp_path` is the D3-class
incident the project memory records (620 GB, ARC 050). What is planted here is
therefore the half the gate DERIVES rather than drives:

* `_required` and `_invoked` read TWO files — `scripts/limiterd.py` and
  `scripts/nixrisk/completions.py` — so a scratch `nix_home` holding two
  hand-written modules is a complete and honest subject for both, and costs three
  directories.

**THE SOURCE-LEVEL PLANTS WERE DRIVEN AGAINST THE SHIPPED GATE**, at ARC 058 /
stage 7, as real edits to the real risk-path files with `git hash-object`
compared before and after each restore:

* **A1** — `closing` deleted from `main()`'s one `CompletionHandler(...)` call,
  the library untouched -> exit 1, *LIBRARY-NOT-DAEMON … `main()` hands it
  NOTHING* + *NOT DRIVEN* + the ARM 4 completeness gap.
* **A2** — `onset.before(...)` deleted from the tick composition -> exit 1,
  *LIBRARY-NOT-DAEMON: per-tick path 'onset' is not composed into
  `loop.attach(ingress=...)`*.
* **A3** — `STALE_OPEN` deleted from `_UNCERTAINTY_TRIGGER` -> exit 1, *the
  condition is detectable and not actionable*.
* **B** — a fifth `UncertaintyCondition` with no producer -> exit 1 naming it.
* **B2** — the same member plus a trigger entry, so it is a required path this
  instrument cannot reach -> exit **2**, *UNCLASSIFIABLE REQUIRED PATH*.
* **C** — the closing path wired and reachable but made unexercisable -> exit 1,
  *NOT DRIVEN* and, correctly, NO library-not-daemon finding.

They are recorded in `RESULTS.md` rather than run here because each costs six
`limiterd` spawns and a live perturbation of a risk-path file.

**TWO DEFECTS THE PLANTS FOUND IN THE GATE ITSELF**, both fixed at their sites
and both regression-guarded below:

1. A1 first exited **2**: the drive's `Missed` propagated to `run`'s catch-all
   and the ARM 2 finding that named the path went with it. *A defect downgraded
   to CANNOT_MEASURE is a defect that never names itself.*
2. A2 first made the required set SHRINK from 23 to 22, because the ingress
   family was derived from `loop.attach(ingress=...)` — the very composition it
   is compared against. Un-wiring a path stopped it being required. The
   vocabulary is now the SHAPE (`def before(self, inner)` + constructed in
   `main()`), so un-wiring leaves the path REQUIRED and NOT INVOKED.
"""
# pylint: disable=invalid-name,redefined-outer-name,missing-function-docstring
# pylint: disable=duplicate-code
# protected-access: this suite's whole subject is the gate's DERIVATION and its
# INVOKED judgement, and both live in module-private functions. Driving them
# through `run()` instead would mean six daemon spawns per plant to reach two
# pure functions.
# pylint: disable=protected-access

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.append(str(REPO / "checks"))

import check_i1_convergence as gate  # pylint: disable=wrong-import-position

#: The five families the gate derives, and what each is derived FROM. Written
#: HERE rather than imported from the gate, deliberately and for the reason
#: `test_check_uncertainty_flatten` gives about its own copy: the gate holds NO
#: copy of any vocabulary, so a copy has to exist somewhere for the derivation to
#: be checkable at all — and a test is where a fixed expectation belongs.
FAMILIES: tuple[str, ...] = (
    "completion",
    "uncertainty",
    "ingress",
    "handler",
    "sender",
)

#: What ARC 058 leaves wired. If a later arc adds a §2A event, a §14 condition, a
#: per-tick composer, a completion collaborator or a protective sender, THIS is
#: one of the two places that must move — the other is the gate's driver table,
#: and a mismatch between them is CANNOT_MEASURE rather than a silent pass.
EXPECTED_PATHS: frozenset[str] = frozenset(
    {
        "completion:on_ack",
        "completion:on_balance",
        "completion:on_cancel",
        "completion:on_fill",
        "completion:on_margin",
        "completion:on_position",
        "completion:on_reject",
        "completion:on_session",
        "uncertainty:stale_open",
        "uncertainty:not_tradable_fill",
        "uncertainty:unarmable_fill",
        "uncertainty:undetailed_poll_fill",
        "ingress:uncertainty",
        "ingress:stopwatch",
        "ingress:onset",
        "ingress:booker",
        "ingress:timeouts",
        "handler:dispatcher",
        "handler:feedback",
        "handler:uncertainty",
        "handler:closing",
        "sender:stops",
        "sender:uncertainty",
    }
)


# --------------------------------------------------------------------------
# The scratch subject. TWO hand-written modules; never a copy of ~/nix.
# --------------------------------------------------------------------------


def _completions_source(*, spec: tuple[str, ...], wired: tuple[str, ...]) -> str:
    """A minimal `completions.py` carrying only what `_required` reads."""
    consts = "\n".join(
        f'EVENT_{name.removeprefix("on_").upper()}: Final[str] = "{name}"'
        for name in spec
    )
    spec_members = "".join(
        f"    EVENT_{name.removeprefix('on_').upper()},\n" for name in spec
    )
    wired_members = ", ".join(
        f"EVENT_{name.removeprefix('on_').upper()}" for name in wired
    )
    return (
        "from typing import Final\n\n"
        f"{consts}\n"
        "SPEC_EVENTS: Final[tuple[str, ...]] = (\n"
        f"{spec_members}"
        ")\n"
        f"WIRED_EVENTS: Final[tuple[str, ...]] = ({wired_members},)\n"
    )


def _limiterd_source(  # pylint: disable=too-many-arguments,too-many-locals
    *,
    conditions: tuple[str, ...] = ("stale_open", "not_tradable_fill"),
    triggered: tuple[str, ...] | None = None,
    composers: tuple[str, ...] = ("onset", "stopwatch"),
    composed: tuple[str, ...] | None = None,
    handler_params: tuple[str, ...] = ("dispatcher", "closing"),
    handler_args: tuple[str, ...] | None = None,
    senders: tuple[str, ...] = ("stops",),
) -> str:
    """A minimal `limiterd.py` carrying only the shapes the gate derives from.

    Every knob here is ONE of the five vocabularies, so a plant is a single
    argument and the un-planted call beside it is the rule-4 pair.
    """
    triggered = conditions if triggered is None else triggered
    composed = composers if composed is None else composed
    handler_args = handler_params if handler_args is None else handler_args
    enum_members = "\n".join(f'    {name.upper()} = "{name}"' for name in conditions)
    trigger_rows = "\n".join(
        f"    UncertaintyCondition.{name.upper()}: FlattenTrigger.UNCERTAINTY,"
        for name in triggered
    )
    # One composer CLASS per composed name, each declaring `before(self, inner)`.
    composer_classes = "\n\n".join(
        f"class {name.title()}Watch:\n"
        f"    def before(self, inner):\n"
        f"        return inner\n"
        for name in composers
    )
    constructions = "\n".join(
        f"    {name} = {name.title()}Watch()" for name in composers
    )
    ingress = "read"
    for name in reversed(composed):
        ingress = f"{name}.before({ingress})"
    params = ", ".join(f"{name}=None" for name in handler_params)
    args = ", ".join(handler_args)
    sender_params = ", ".join(senders)
    return (
        "import enum\n"
        "from typing import Final\n\n\n"
        "class FlattenTrigger(enum.Enum):\n"
        '    UNCERTAINTY = "uncertainty"\n\n\n'
        "class UncertaintyCondition(enum.Enum):\n"
        f"{enum_members or '    pass'}\n\n\n"
        "class CompletionHandler:\n"
        f"    def __init__(self, {params}):\n"
        "        self._all = 1\n\n\n"
        "class ProtectiveSenders:\n"
        f"    def __init__(self, {sender_params}):\n"
        "        self._all = 1\n\n"
        "    def send(self, payload):\n"
        "        return payload\n\n\n"
        f"{composer_classes}\n\n"
        "_UNCERTAINTY_TRIGGER: Final[dict] = {\n"
        f"{trigger_rows}\n"
        "}\n\n\n"
        "def main():\n"
        f"{constructions}\n"
        "    senders = ProtectiveSenders(1)\n"
        f"    completion_handler = CompletionHandler({args})\n"
        "    loop.attach(\n"
        f"        ingress={ingress},\n"
        "        handler=LoopHandler(commands, completion_handler).handle,\n"
        "        sender_send=senders.send,\n"
        "    )\n"
    )


def _scratch_tree(  # pylint: disable=too-many-arguments
    tmp_path: Path,
    *,
    spec: tuple[str, ...] = ("on_fill", "on_cancel"),
    wired: tuple[str, ...] = ("on_fill", "on_cancel"),
    **limiterd: Any,
) -> Path:
    """A `nix_home` holding TWO files. Never a copy of `~/nix` (project memory)."""
    home = tmp_path / "nix"
    (home / "scripts" / "nixrisk").mkdir(parents=True)
    (home / "scripts" / "limiterd.py").write_text(
        _limiterd_source(**limiterd), encoding="utf-8"
    )
    (home / "scripts" / "nixrisk" / "completions.py").write_text(
        _completions_source(spec=spec, wired=wired), encoding="utf-8"
    )
    return home


# --------------------------------------------------------------------------
# NON-VACUITY FIRST — the REAL tree derives the real set and judges it INVOKED
# --------------------------------------------------------------------------


def test_the_REAL_tree_derives_EXACTLY_the_paths_this_arc_leaves_wired() -> None:
    required = gate._required(REPO)
    assert set(required) == set(EXPECTED_PATHS), sorted(
        set(required) ^ set(EXPECTED_PATHS)
    )


def test_the_REAL_tree_judges_EVERY_required_path_DAEMON_INVOKED() -> None:
    """I1's structural half, over the shipped tree. No plant, no daemon."""
    required = gate._required(REPO)
    invoked, findings = gate._invoked(REPO, required)
    assert not findings, findings
    assert invoked == set(required), sorted(set(required) - invoked)


def test_every_derived_path_belongs_to_ONE_of_the_FIVE_families() -> None:
    required = gate._required(REPO)
    families = {path.partition(":")[0] for path in required}
    assert families == set(FAMILIES), sorted(families ^ set(FAMILIES))


def test_the_GATE_HOLDS_NO_COPY_of_any_vocabulary(tmp_path: Path) -> None:
    """`check_flatten` ARM 6's lesson: a hand-written set is a set that goes stale.

    Handed a subject whose vocabularies are NOTHING like the real tree's, the
    derivation must return that subject's set — never the real one, and never a
    constant. A gate that answered the same 23 paths here would be reading its
    own memory rather than its subject.
    """
    home = _scratch_tree(
        tmp_path,
        spec=("on_zork",),
        wired=("on_zork",),
        conditions=("zork_condition",),
        composers=("zork",),
        handler_params=("zorkdispatcher",),
        senders=("zorksender",),
    )
    assert set(gate._required(home)) == {
        "completion:on_zork",
        "uncertainty:zork_condition",
        "ingress:zork",
        "handler:zorkdispatcher",
        "sender:zorksender",
    }


# --------------------------------------------------------------------------
# THE PLANTS — each must go RED and NAME its site
# --------------------------------------------------------------------------


def test_PLANT_A1_a_handler_collaborator_the_daemon_hands_NOTHING(
    tmp_path: Path,
) -> None:
    """The whole of ARC D, un-wired at ONE call site. Its library is intact."""
    home = _scratch_tree(tmp_path, handler_args=("dispatcher",))
    required = gate._required(home)
    invoked, findings = gate._invoked(home, required)
    assert "handler:closing" in required
    assert "handler:closing" not in invoked
    assert any(
        "LIBRARY-NOT-DAEMON" in why and "'closing'" in why for _site, why in findings
    ), findings


def test_PLANT_A1b_an_EXPLICIT_None_is_the_same_as_absent(tmp_path: Path) -> None:
    """`closing=None` keeps the arity and removes the path. It must not pass."""
    home = _scratch_tree(tmp_path, handler_args=("dispatcher", "None"))
    required = gate._required(home)
    invoked, findings = gate._invoked(home, required)
    assert "handler:closing" not in invoked
    assert any("LIBRARY-NOT-DAEMON" in why for _site, why in findings), findings


def test_PLANT_A2_a_per_tick_path_dropped_from_the_composition(
    tmp_path: Path,
) -> None:
    """THE REGRESSION GUARD for defect 2 above: the required set MUST NOT shrink."""
    home = _scratch_tree(
        tmp_path, composers=("onset", "stopwatch"), composed=("stopwatch",)
    )
    required = gate._required(home)
    assert "ingress:onset" in required, sorted(required)
    invoked, findings = gate._invoked(home, required)
    assert "ingress:onset" not in invoked
    assert any(
        "LIBRARY-NOT-DAEMON" in why and "'onset'" in why for _site, why in findings
    ), findings


def test_PLANT_A3_a_condition_with_NO_trigger_is_detectable_not_actionable(
    tmp_path: Path,
) -> None:
    home = _scratch_tree(
        tmp_path,
        conditions=("stale_open", "not_tradable_fill"),
        triggered=("not_tradable_fill",),
    )
    required = gate._required(home)
    invoked, findings = gate._invoked(home, required)
    assert "uncertainty:stale_open" in required
    assert "uncertainty:stale_open" not in invoked
    assert any("stale_open" in why for _site, why in findings), findings


def test_PLANT_B_a_required_path_with_NO_handler_at_all(tmp_path: Path) -> None:
    """A fifth §14 condition nothing produces. It is REQUIRED and not invoked."""
    home = _scratch_tree(
        tmp_path,
        conditions=("stale_open", "not_tradable_fill", "orphan_position"),
        triggered=("stale_open", "not_tradable_fill"),
    )
    required = gate._required(home)
    invoked, findings = gate._invoked(home, required)
    assert "uncertainty:orphan_position" in required
    assert "uncertainty:orphan_position" not in invoked
    assert any("orphan_position" in why for _site, why in findings), findings


def test_PLANT_the_handler_is_BUILT_and_NEVER_REACHES_the_loop(
    tmp_path: Path,
) -> None:
    """`main()` builds the CompletionHandler and `attach(handler=)` ignores it."""
    source = _limiterd_source().replace(
        "handler=LoopHandler(commands, completion_handler).handle",
        "handler=LoopHandler(commands).handle",
    )
    home = tmp_path / "nix"
    (home / "scripts" / "nixrisk").mkdir(parents=True)
    (home / "scripts" / "limiterd.py").write_text(source, encoding="utf-8")
    (home / "scripts" / "nixrisk" / "completions.py").write_text(
        _completions_source(spec=("on_fill",), wired=("on_fill",)), encoding="utf-8"
    )
    required = gate._required(home)
    invoked, findings = gate._invoked(home, required)
    assert "completion:on_fill" not in invoked
    assert any("no route into" in why for _site, why in findings), findings


def test_PLANT_an_EMPTY_composition_is_CANNOT_MEASURE_not_a_pass(
    tmp_path: Path,
) -> None:
    """A build that composes no per-tick work has no tick. It may not read clean."""
    source = _limiterd_source().replace(
        "    def before(self, inner):", "    def after(self, inner):"
    )
    home = tmp_path / "nix"
    (home / "scripts" / "nixrisk").mkdir(parents=True)
    (home / "scripts" / "limiterd.py").write_text(source, encoding="utf-8")
    (home / "scripts" / "nixrisk" / "completions.py").write_text(
        _completions_source(spec=("on_fill",), wired=("on_fill",)), encoding="utf-8"
    )
    with pytest.raises(gate.Cannot) as raised:
        gate._required(home)
    assert "before(self, inner)" in str(raised.value)


def test_a_MISSED_drive_is_a_FINDING_and_never_an_escaping_exception() -> None:
    """THE REGRESSION GUARD for defect 1 above (`_step`).

    PLANT A1's first run exited 2 because a `Missed` reached `run`'s catch-all,
    taking the ARM 2 finding with it. `_step` must swallow it INTO the findings —
    named, with the daemon's last published status attached.
    """
    findings: list[tuple[str, str]] = []

    def _never() -> None:
        raise gate.Missed("the closing fill to be RECONCILED", {"closing": None})

    assert gate._step(_never, findings) is None
    assert findings and "NOT DRIVEN" in findings[0][1]
    assert "RECONCILED" in findings[0][1]


def test_a_step_that_SUCCEEDS_adds_no_finding() -> None:
    """The other half of the same control: `_step` must not invent findings."""
    findings: list[tuple[str, str]] = []
    assert gate._step(lambda: {"ok": True}, findings) == {"ok": True}
    assert not findings


# --------------------------------------------------------------------------
# RULE 4 — PLANT BOTH: the same judgement, planted and un-planted
# --------------------------------------------------------------------------


@pytest.mark.parametrize("planted", [True, False])
def test_RULE_4_PLANT_BOTH_the_same_judgement_red_then_green(
    tmp_path: Path, planted: bool
) -> None:
    """The gate's verdict must FOLLOW the subject, not the run.

    A check that only ever reports one colour has not been shown to be measuring
    anything. Same two functions, same call shape, ONE difference in the subject:
    whether `main()` hands the closing collaborator to its `CompletionHandler`.
    """
    home = _scratch_tree(
        tmp_path / ("red" if planted else "green"),
        handler_args=("dispatcher",) if planted else ("dispatcher", "closing"),
    )
    required = gate._required(home)
    invoked, findings = gate._invoked(home, required)
    assert "handler:closing" in required, sorted(required)
    if planted:
        assert "handler:closing" not in invoked
        assert findings and any("LIBRARY-NOT-DAEMON" in why for _s, why in findings)
    else:
        assert invoked == set(required), sorted(set(required) - invoked)
        assert not findings, findings
