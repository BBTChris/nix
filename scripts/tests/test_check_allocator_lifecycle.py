"""ARC 032 Stage 1 / C — the CAN-FAIL suite for `checks/check_allocator_lifecycle.py`.

Doctrine C.2: *a gate is guilty until shown able to say no.* This file is that
demonstration, and it is the §0e artifact — a committed, runnable control that
drives the SHIPPED gate's own bytes RED.

**Non-vacuity first** (the real tree and an untouched copy both PASS), then one
plant per property the gate claims to measure, each required to redden AND to
NAME its site and its condition, then the plant removed and the same tree green.

**No plant touches a production artifact** (doctrine C.8). Every control builds a
throwaway `nix_home` under `tmp_path` holding COPIES of the subjects and of
everything they import, perturbs a COPY, and points the gate at it. The last
test asserts the live tree is still green after the whole suite has run.

The plants are the wrong implementations a reader would plausibly write, not
arbitrary corruption:

  * the screened set moved off §4's own word — a state name transcribed once and
    then drifted;
  * the screen deleted — the dying strategy stays eligible, which is the whole
    §4:284-286 defect and the one no fixture without a transition can see;
  * the screen LATCHED — a refusal that never releases, which passes every test
    that only drives the dying half;
  * the freshness guard narrowed to `picture is None` — a STALE mirror still
    holding a picture is read anyway (§6.4's "carry on with the last value");
  * the contention pass ignoring the screen — the module is right and nobody
    consults it;
  * the screen failing OPEN on a view that raises;
  * a recovery-driving verb, and a coroutine, on the Allocator's side;
  * an Allocator-side PRODUCER of the screened state — the authority split
    crossed in the direction §2 forbids;
  * the producer removed from the Limiter side, so the transition drives a state
    nothing publishes and the census can no longer discriminate.

Every control asserts the REASON — the site and the named condition — never the
exit code or the status alone (check contract v2 §11).
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code

from __future__ import annotations

import ast
import shutil
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.append(str(REPO / "checks"))

import check_allocator_lifecycle as gate  # pylint: disable=wrong-import-position
from nixalloc.seam import PositionState  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)

LIFECYCLE = "scripts/nixalloc/lifecycle.py"
CONTENTION = "scripts/nixalloc/contention.py"
FLATTEN = "scripts/nixrisk/flatten.py"
SPEC = "docs/nics_risk_subsystem_spec_v1.3.md"

COPIED = (
    LIFECYCLE,
    CONTENTION,
    "scripts/nixalloc/__init__.py",
    "scripts/nixalloc/seam.py",
    "scripts/nixalloc/mirror.py",
    "scripts/nixrisk/__init__.py",
    "scripts/nixrisk/seam.py",
    "scripts/nixrisk/picture.py",
    "scripts/nixrisk/reservations.py",
    FLATTEN,
    "scripts/nixbus/__init__.py",
    "scripts/nixbus/statebus.py",
    SPEC,
)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """A throwaway tree carrying COPIES of the subjects and their imports."""
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


def _append(home: Path, rel: str, addition: str) -> None:
    """Add to a COPIED file."""
    path = home / rel
    path.write_text(path.read_text(encoding="utf-8") + addition, encoding="utf-8")


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


def _unmeasurable(result, *, why_contains: str) -> None:
    assert result.status is Status.CANNOT_MEASURE, (
        f"expected CANNOT_MEASURE, got {result.status!r}: {result.detail}"
    )
    assert why_contains in (result.detail or ""), (
        f"detail does not name {why_contains!r}: {result.detail}"
    )


# ==========================================================================
# NON-VACUITY FIRST. A gate that cannot pass clean measures nothing dirty.
# ==========================================================================


def test_the_REAL_tree_and_the_COPY_both_pass(home: Path) -> None:
    """The gate is green on the shipped tree and on an untouched copy of it."""
    live = _run(REPO)
    assert live.status is Status.PASS, live.detail
    assert "5 arms driving the SHIPPED" in (live.evidence or ""), live.evidence
    copied = _run(home)
    assert copied.status is Status.PASS, copied.detail


def test_the_evidence_reports_a_transition_that_actually_MOVED(home: Path) -> None:
    """§7.12/3-4: a green whose sequence never changed proves nothing.

    The evidence line is the record, so the record has to show the change. Three
    distinct versions, one of them carrying a screened row, and the eligibility
    value moving True -> False -> True.
    """
    evidence = _run(home).evidence or ""
    assert "eligible=True" in evidence and "eligible=False" in evidence, evidence
    assert "1 screened row(s)" in evidence, evidence
    assert "REAL ipc:// socket" in evidence, evidence


def test_the_gate_DECLARES_its_two_subjects() -> None:
    """Coverage is what SUBJECTS names; the ratchet can see nothing else."""
    assert set(gate.SUBJECTS) == {LIFECYCLE, CONTENTION}


def test_the_gate_is_NON_CORRECTABLE_with_a_stated_reason() -> None:
    """Rule 1/2: a gate that could edit either side manufactures its own green."""
    assert gate.CORRECTABLE is False
    assert "manufacturing its own green" in gate.NON_CORRECTABLE_REASON


def test_the_gate_spells_NO_lifecycle_state_in_its_EXECUTABLE_code() -> None:
    """ARM 1's reference side is parsed from the spec, never transcribed here.

    Measured over the AST — string constants that are not docstrings, plus
    identifiers — rather than over the raw bytes: the gate's PROSE names the
    state while explaining what it does, and a check that reddened on its own
    explanation would be unusable (the carve-out `check_allocator_caps`'s suite
    makes for its bucket names).
    """
    tree = ast.parse(Path(gate.__file__).read_text(encoding="utf-8"))
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        )
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    executable = {
        node.value.lower()
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    } | {node.id.lower() for node in ast.walk(tree) if isinstance(node, ast.Name)}
    for state in PositionState:
        assert state.value not in executable, (
            f"{state.value!r} is spelled in the gate's executable code — a gate "
            "that writes down its own expected side is a gate agreeing with "
            "itself, and ARM 1 parses that word out of the frozen spec"
        )


# ==========================================================================
# ARM 1 — the screened state is the SPEC's
# ==========================================================================


def test_a_screened_set_that_drifted_off_the_SPEC_reddens(home: Path) -> None:
    """The state a strategy is refused capital for is §4's, not the module's."""
    _plant(
        home,
        LIFECYCLE,
        "frozenset({PositionState.CLOSING})",
        "frozenset({PositionState.CLOSED})",
    )
    _red(
        _run(home),
        site_contains="lifecycle.py:IN_FLIGHT_CLOSING",
        why_contains="locked sentence names",
    )


def test_the_drifted_set_removed_leaves_the_same_tree_GREEN(home: Path) -> None:
    """The plant, then its removal. A red that never goes green is not a control."""
    original = (home / LIFECYCLE).read_text(encoding="utf-8")
    _plant(
        home,
        LIFECYCLE,
        "frozenset({PositionState.CLOSING})",
        "frozenset({PositionState.CLOSED})",
    )
    assert _run(home).status is Status.FAIL_NEEDS_OPERATOR
    (home / LIFECYCLE).write_text(original, encoding="utf-8")
    restored = _run(home)
    assert restored.status is Status.PASS, restored.detail


def test_a_MOVED_spec_sentence_is_CANNOT_MEASURE_not_a_quiet_agreement(
    home: Path,
) -> None:
    """§7.12/2: an unmatched anchor yields an empty expected set."""
    _plant(home, SPEC, "reads as **in-flight-closing**", "reads as *in flight closing*")
    _unmeasurable(_run(home), why_contains="did not match inside section")


# ==========================================================================
# ARM 2 — THE TRANSITION, and it is the plant that matters
# ==========================================================================


def test_a_screen_that_ADMITS_THE_DYING_reddens(home: Path) -> None:
    """THE FALSIFIER. §4:284-286 deleted: the dying strategy keeps its capital."""
    _plant(home, LIFECYCLE, "    if closing:\n", "    if False:  # screen removed\n")
    _red(
        _run(home),
        site_contains="lifecycle.py:eligibility_from_mirror",
        why_contains="still counted ELIGIBLE for new capital",
    )


def test_a_screen_that_LATCHES_reddens(home: Path) -> None:
    """A refusal that never releases: eligibility becomes a one-way door.

    The mirror image of the plant above, and the reason both are driven: a
    screen hard-wired to False refuses the dying strategy perfectly and would
    pass any test that only looked at the middle step.
    """
    _plant(home, LIFECYCLE, "    if closing:\n", "    if True:  # never releases\n")
    _red(
        _run(home),
        site_contains="lifecycle.py:eligibility_from_mirror",
        why_contains="a screen that refuses a healthy strategy",
    )


def test_a_screen_that_reads_a_STALE_mirror_anyway_reddens(home: Path) -> None:
    """§6.4: the rule for a stale cache is refuse, never the last value.

    The guard is narrowed to `picture is None`, which still refuses the mirror
    that never heard anything — so only the stale-but-HELD control can see it.
    """
    _plant(
        home,
        LIFECYCLE,
        "    if not snapshot.sizeable or snapshot.picture is None:\n"
        "        return CapitalEligibility(",
        "    if snapshot.picture is None:\n        return CapitalEligibility(",
    )
    _red(
        _run(home),
        site_contains="lifecycle.py:eligibility_from_mirror",
        why_contains="never carry on with the last value",
    )


def test_a_PRODUCER_that_stops_publishing_the_state_reddens(home: Path) -> None:
    """§7.12/3: with nothing producing the state, the arm measures nothing.

    Planted on the Limiter side — `nixrisk/flatten.py` republishes a held
    position as CLOSING — so the transition still runs and still publishes three
    versions; only the middle one no longer carries the state.
    """
    _plant(
        home,
        FLATTEN,
        "                state=PositionState.CLOSING,",
        "                state=PositionState.OPEN,",
    )
    _red(
        _run(home),
        site_contains="lifecycle.py:IN_FLIGHT_CLOSING",
        why_contains="below the discriminator floor",
    )


# ==========================================================================
# ARM 3 — the contention pass
# ==========================================================================


def test_a_contention_pass_that_IGNORES_the_screen_reddens(home: Path) -> None:
    """The module can be right and the pass can still hand capital to the dying."""
    _plant(
        home,
        CONTENTION,
        "        if verdict.eligible:\n",
        "        if True:  # the screen is consulted and discarded\n",
    )
    _red(
        _run(home),
        site_contains="contention.py:rank_eligible",
        why_contains="still in the contention ordering",
    )


def test_a_screen_that_refuses_EVERYONE_reddens(home: Path) -> None:
    """A screen that empties the race passes any test watching only the dying."""
    _plant(
        home,
        CONTENTION,
        "        if verdict.eligible:\n",
        "        if False:  # nobody is ever eligible\n",
    )
    _red(
        _run(home),
        site_contains="contention.py:rank_eligible",
        why_contains="was screened out too",
    )


def test_a_refusal_that_NAMES_NOTHING_reddens(home: Path) -> None:
    """§18: a contender that vanishes without a reason is unactionable."""
    _plant(
        home,
        CONTENTION,
        "                    reason=verdict.reason,",
        '                    reason="",',
    )
    _red(
        _run(home),
        site_contains="contention.py:rank_eligible",
        why_contains="names neither the trade nor the state",
    )


def test_a_screen_that_FAILS_OPEN_on_a_raising_view_reddens(home: Path) -> None:
    """Fail closed: an unanswerable safety screen must never admit."""
    _plant(
        home,
        CONTENTION,
        "            continue\n        if verdict.eligible:",
        "            ranked.append(contender)\n            continue\n"
        "        if verdict.eligible:",
    )
    _red(
        _run(home),
        site_contains="contention.py:rank_eligible",
        why_contains="fail-OPEN direction",
    )


def test_a_screen_that_PROPAGATES_the_exception_reddens(home: Path) -> None:
    """§6.6:468's neighbour: an exception on the pass is order flow stalling."""
    _plant(
        home,
        CONTENTION,
        "        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001\n"
        "            refused.append(",
        "        except ZeroDivisionError as exc:  # noqa: BLE001\n"
        "            refused.append(",
    )
    _red(
        _run(home),
        site_contains="contention.py:rank_eligible",
        why_contains="escape onto the contention pass",
    )


# ==========================================================================
# ARM 5 — the boundary: reflects, never drives
# ==========================================================================


@pytest.mark.parametrize(
    "verb", ["flatten", "deregister", "kill", "relaunch", "quarantine", "heartbeat"]
)
def test_EVERY_recovery_verb_is_caught_in_turn(home: Path, verb: str) -> None:
    """The forbidden list is driven member by member, never as a whole."""
    _append(home, LIFECYCLE, f"\n\ndef {verb}(strategy_id):\n    return strategy_id\n")
    _red(
        _run(home),
        site_contains=f"lifecycle.py:{verb}",
        why_contains=f"{verb!r}",
    )


def test_a_COROUTINE_on_the_screen_path_reddens(home: Path) -> None:
    """A suspension point inside §16 U1's single pass is a window (§3)."""
    _append(
        home,
        LIFECYCLE,
        "\n\nasync def screen_later(strategy_id):\n    return strategy_id\n",
    )
    _red(
        _run(home),
        site_contains="lifecycle.py:screen_later",
        why_contains="declared `async def`",
    )


def test_an_ALLOCATOR_SIDE_PRODUCER_of_the_screened_state_reddens(home: Path) -> None:
    """§2: the Limiter publishes recovery, the Allocator reflects it."""
    _append(
        home,
        LIFECYCLE,
        "\n\ndef _fabricate(row):\n"
        "    return PositionRow(\n"
        "        trade_id=row.trade_id,\n"
        "        symbol=row.symbol,\n"
        "        strategy_id=row.strategy_id,\n"
        "        size=row.size,\n"
        "        margin=row.margin,\n"
        "        state=PositionState.CLOSING,\n"
        "        stop_distance=row.stop_distance,\n"
        "    )\n",
    )
    _red(
        _run(home),
        site_contains="lifecycle.py:state=",
        why_contains="CONSTRUCTS a position row in the screened state",
    )


# ==========================================================================
# THE MEASURE-NOTHING ROUTES (§7.12), each driven rather than argued
# ==========================================================================


def test_a_MISSING_subject_is_CANNOT_MEASURE_and_never_a_PASS(home: Path) -> None:
    """§17: a property proven while its subject is unavailable is not proven."""
    (home / LIFECYCLE).unlink()
    _unmeasurable(_run(home), why_contains="no such file")


def test_an_UNIMPORTABLE_subject_is_CANNOT_MEASURE(home: Path) -> None:
    """A syntax error is not a finding about §4; it is an unread subject."""
    _append(home, LIFECYCLE, "\nthis is not python\n")
    _unmeasurable(_run(home), why_contains="cannot import the subjects")


def test_an_EMPTY_tree_does_not_fall_through_to_the_LIVE_repository(
    tmp_path: Path,
) -> None:
    """D3.124: `checks/_preamble.py` leaves the real `scripts/` on `sys.path`.

    A name-based import against an empty tree resolves to the live repository
    and the gate reports a green about a tree it never read.
    """
    _unmeasurable(_run(tmp_path), why_contains="no such file")


def test_the_gate_ANSWERS_the_standing_question_in_its_docstring() -> None:
    """§7.12 is required of every gate at the point it is built."""
    doc = gate.__doc__ or ""
    assert "WHAT WOULD HAVE TO BE TRUE FOR THIS GATE TO PASS" in doc
    assert doc.count("CLOSED:") >= 6, "a route with no mechanism is not closed"


def test_the_gate_states_what_it_CANNOT_prove() -> None:
    """A green here must not read as coverage of §4's unbuilt recovery half."""
    doc = gate.__doc__ or ""
    assert "WHAT THIS GATE CANNOT PROVE" in doc
    assert "strategy-death recovery" in doc
    assert "R5" in doc and "R4" in doc


def test_the_gate_PRINTS_the_absent_producer_rather_than_restating_it() -> None:
    """The mandate: the gate itself must say who publishes this state.

    Read out of `lifecycle.RECOVERY_PRODUCER` and `lifecycle.SCORE_BOUNDARY` so
    there is ONE home for each sentence (directive 3) — a second copy inside the
    gate is the restated mutable fact directive 3 forbids.
    """
    evidence = _run(REPO).evidence or ""
    assert "WHAT PRODUCES THIS STATE" in evidence
    assert "DOES NOT EXIST in this tree" in evidence
    assert "WHAT IS NOT HERE" in evidence
    assert "Scoring process" in evidence


def test_no_plant_touched_the_repository() -> None:
    """Doctrine C.8, asserted rather than promised: the live tree is still green."""
    live = _run(REPO)
    assert live.status is Status.PASS, live.detail
